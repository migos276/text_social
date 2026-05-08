import math
import random
import uuid
from collections import Counter, defaultdict
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import OperationalError, transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.feed.models import (
    FeedImpression,
    PostAnalytics,
    PostDistribution,
    PostInteraction,
    PostPoolRecipient,
    UserBanditArm,
    UserGenreInterest,
    UserInterestProfile,
    UserTagInterest,
    ViralPost,
)
from apps.posts.models import Post

User = get_user_model()


INTERACTION_WEIGHTS = {
    PostInteraction.SIGNAL_VIEW: 1.0,
    PostInteraction.SIGNAL_LIKE: 3.0,
    PostInteraction.SIGNAL_COMMENT: 4.0,
    PostInteraction.SIGNAL_SHARE: 5.0,
    PostInteraction.SIGNAL_BOOKMARK: 4.0,
    PostInteraction.SIGNAL_REPORT: -6.0,
    PostInteraction.SIGNAL_SCROLL: -2.5,
}

FEED_BUCKET_WEIGHTS = {
    'targeted': 0.70,
    'popular': 0.15,
    'exploration': 0.10,
    'wildcard': 0.05,
}

POOL_SIZES = [500, 5000, 50000, 500000]
POOL_THRESHOLDS = {
    1: 0.12,
    2: 0.15,
    3: 0.18,
}

INTEREST_WINDOW_DAYS = 7
RECENT_CATEGORY_WINDOW_HOURS = 24
VIRAL_ACTIVE_HOURS = 3
SOFTMAX_TEMPERATURE = 0.55
UCB_EXPLORATION = 1.15
MMR_LAMBDA = 0.72
PROFILE_REFRESH_MIN_INTERVAL_SECONDS = 30


def _get_or_create_analytics(post):
    analytics, _ = PostAnalytics.objects.get_or_create(post=post)
    return analytics


def _get_or_create_distribution(post):
    distribution, _ = PostDistribution.objects.get_or_create(
        post=post,
        defaults={
            'current_pool': 1,
            'current_pool_size': POOL_SIZES[0],
            'next_pool_size': POOL_SIZES[1],
        },
    )
    return distribution


def _normalize_scores(rows, attr):
    total = sum(max(getattr(row, attr), 0) for row in rows)
    if total <= 0:
        return {}
    return {
        (row.genre if hasattr(row, 'genre') else row.tag.name): round(max(getattr(row, attr), 0) / total, 4)
        for row in rows
    }


def ensure_user_interest_profile(user):
    profile, _ = UserInterestProfile.objects.get_or_create(user=user)
    return profile


def assign_post_to_pool_users(post, pool_number, target_size):
    """Assign a post to a random recipient pool for staged diffusion."""

    existing_user_ids = set(
        PostPoolRecipient.objects.filter(post=post).values_list('user_id', flat=True)
    )
    candidate_user_ids = list(
        User.objects.exclude(id=post.author_id).exclude(id__in=existing_user_ids).values_list('id', flat=True)
    )
    if not candidate_user_ids:
        return 0

    sample_size = min(target_size, len(candidate_user_ids))
    selected_ids = random.sample(candidate_user_ids, sample_size)
    PostPoolRecipient.objects.bulk_create([
        PostPoolRecipient(post=post, user_id=user_id, pool_number=pool_number)
        for user_id in selected_ids
    ])
    return sample_size


def _recent_interactions_queryset(user):
    cutoff = timezone.now() - timedelta(days=INTEREST_WINDOW_DAYS)
    return (
        PostInteraction.objects
        .filter(user=user, created_at__gte=cutoff)
        .select_related('post')
        .prefetch_related('post__tags')
        .order_by('-created_at')
    )


def _interaction_reward(interaction):
    reward = INTERACTION_WEIGHTS.get(interaction.signal, 0)
    reward += interaction.read_progress * 2
    reward += 1.5 if interaction.completed_read else 0
    reward += interaction.reread_count * 1.2
    if interaction.is_quick_scroll:
        reward -= 2
    return reward


def _update_bandit_arm(user, arm_type, arm_key, reward):
    arm, _ = UserBanditArm.objects.get_or_create(
        user=user,
        arm_type=arm_type,
        arm_key=arm_key,
    )
    arm.impressions += 1
    if reward > 1:
        arm.successes += 1
    elif reward < 0:
        arm.failures += 1
    arm.total_reward += reward
    arm.save()
    return arm


def _update_bandit_after_interaction(user, post, reward, interaction):
    bucket = interaction.metadata.get('recommendation_bucket')
    if bucket == 'wildcard':
        _update_bandit_arm(user, UserBanditArm.ARM_WILDCARD, 'wildcard', reward)

    _update_bandit_arm(user, UserBanditArm.ARM_GENRE, post.genre, reward)
    for tag in post.tags.all():
        _update_bandit_arm(user, UserBanditArm.ARM_TAG, tag.name, reward)


def _should_refresh_interest_profile(user):
    profile = (
        UserInterestProfile.objects
        .filter(user=user)
        .only('updated_at')
        .first()
    )
    if not profile or not profile.updated_at:
        return True

    elapsed = timezone.now() - profile.updated_at
    return elapsed >= timedelta(seconds=PROFILE_REFRESH_MIN_INTERVAL_SECONDS)


def record_post_interaction(user, post, *, signal, reading_time_ms=0, read_progress=0, completed_read=False,
                            reread_count=0, is_quick_scroll=False, metadata=None):
    """Persist one event, refresh analytics and update the sliding interest window."""

    interaction = PostInteraction.objects.create(
        user=user,
        post=post,
        signal=signal,
        reading_time_ms=reading_time_ms,
        read_progress=read_progress,
        completed_read=completed_read,
        reread_count=reread_count,
        is_quick_scroll=is_quick_scroll,
        metadata=metadata or {},
    )
    reward = _interaction_reward(interaction)

    try:
        refresh_post_analytics(post)
    except OperationalError:
        pass

    if _should_refresh_interest_profile(user):
        try:
            update_user_interest_profile(user)
        except OperationalError:
            pass

    try:
        _update_bandit_after_interaction(user, post, reward, interaction)
    except OperationalError:
        pass

    return interaction


def refresh_post_analytics(post):
    """Recompute denormalized counters used by ranking and viral detection."""

    analytics = _get_or_create_analytics(post)
    interactions = PostInteraction.objects.filter(post=post)

    impressions = interactions.count()
    views = interactions.exclude(signal=PostInteraction.SIGNAL_SCROLL).count()
    unique_viewers = interactions.values('user_id').distinct().count()
    likes = interactions.filter(signal=PostInteraction.SIGNAL_LIKE).count()
    comments = interactions.filter(signal=PostInteraction.SIGNAL_COMMENT).count()
    shares = interactions.filter(signal=PostInteraction.SIGNAL_SHARE).count()
    bookmarks = interactions.filter(signal=PostInteraction.SIGNAL_BOOKMARK).count()
    reports = interactions.filter(signal=PostInteraction.SIGNAL_REPORT).count()
    complete_reads = interactions.filter(completed_read=True).count()
    rereads = sum(item.reread_count for item in interactions.only('reread_count'))
    quick_scrolls = interactions.filter(is_quick_scroll=True).count()
    total_reading_time_ms = sum(item.reading_time_ms for item in interactions.only('reading_time_ms'))
    progress_values = [item.read_progress for item in interactions.only('read_progress')]
    avg_read_progress = (sum(progress_values) / len(progress_values)) if progress_values else 0

    positive = (
        views * INTERACTION_WEIGHTS[PostInteraction.SIGNAL_VIEW]
        + likes * INTERACTION_WEIGHTS[PostInteraction.SIGNAL_LIKE]
        + comments * INTERACTION_WEIGHTS[PostInteraction.SIGNAL_COMMENT]
        + shares * INTERACTION_WEIGHTS[PostInteraction.SIGNAL_SHARE]
        + bookmarks * INTERACTION_WEIGHTS[PostInteraction.SIGNAL_BOOKMARK]
        + complete_reads * 2.5
        + rereads * 1.5
    )
    negative = (
        quick_scrolls * abs(INTERACTION_WEIGHTS[PostInteraction.SIGNAL_SCROLL])
        + reports * abs(INTERACTION_WEIGHTS[PostInteraction.SIGNAL_REPORT])
    )
    engagement_score = (positive - negative) / max(impressions, 1)
    engagement_score += avg_read_progress * 2

    analytics.impressions = impressions
    analytics.views = views
    analytics.unique_viewers = unique_viewers
    analytics.likes = likes
    analytics.comments = comments
    analytics.shares = shares
    analytics.bookmarks = bookmarks
    analytics.reports = reports
    analytics.complete_reads = complete_reads
    analytics.rereads = rereads
    analytics.quick_scrolls = quick_scrolls
    analytics.total_reading_time_ms = total_reading_time_ms
    analytics.avg_read_progress = round(avg_read_progress, 4)
    analytics.engagement_score = round(engagement_score, 4)
    analytics.last_engagement_at = timezone.now()
    analytics.save()

    distribution = _get_or_create_distribution(post)
    distribution.engagement_rate = compute_distribution_engagement_rate(analytics)
    distribution.save(update_fields=['engagement_rate', 'updated_at'])
    return analytics


def compute_distribution_engagement_rate(analytics):
    """Compact pool-graduation metric."""

    base = (
        analytics.likes * 1.5
        + analytics.comments * 2
        + analytics.shares * 2.5
        + analytics.bookmarks * 1.5
        + analytics.complete_reads * 1.2
        + analytics.rereads * 1.1
    )
    penalty = analytics.quick_scrolls * 1.5 + analytics.reports * 3
    return round(max((base - penalty) / max(analytics.impressions, 1), 0), 4)


@transaction.atomic
def update_user_interest_profile(user):
    """Sliding 7-day interest window used as the canonical user profile."""

    profile = ensure_user_interest_profile(user)
    cutoff = timezone.now() - timedelta(days=INTEREST_WINDOW_DAYS)
    interactions = list(
        PostInteraction.objects
        .filter(user=user, created_at__gte=cutoff)
        .select_related('post')
        .prefetch_related('post__tags')
    )

    UserGenreInterest.objects.filter(user=user).delete()
    UserTagInterest.objects.filter(user=user).delete()

    genre_scores = defaultdict(float)
    genre_counts = Counter()
    tag_scores = defaultdict(float)
    tag_counts = Counter()

    for interaction in interactions:
        reward = _interaction_reward(interaction)
        genre_scores[interaction.post.genre] += reward
        genre_counts[interaction.post.genre] += 1
        for tag in interaction.post.tags.all():
            tag_scores[tag.id] += reward
            tag_counts[tag.id] += 1

    genre_rows = [
        UserGenreInterest(
            user=user,
            genre=genre,
            score=max(score, 0),
            interactions_count=genre_counts[genre],
        )
        for genre, score in genre_scores.items()
    ]
    if genre_rows:
        UserGenreInterest.objects.bulk_create(genre_rows)

    tag_rows = [
        UserTagInterest(
            user=user,
            tag_id=tag_id,
            score=max(score, 0),
            interactions_count=tag_counts[tag_id],
        )
        for tag_id, score in tag_scores.items()
    ]
    if tag_rows:
        UserTagInterest.objects.bulk_create(tag_rows)

    top_genres = UserGenreInterest.objects.filter(user=user).order_by('-score', '-updated_at')[:10]
    top_tags = UserTagInterest.objects.filter(user=user).select_related('tag').order_by('-score', '-updated_at')[:15]

    profile.top_genres = _normalize_scores(top_genres, 'score')
    profile.top_tags = _normalize_scores(top_tags, 'score')
    profile.last_interaction_at = interactions[0].created_at if interactions else profile.last_interaction_at
    profile.updated_at = timezone.now()
    profile.save(update_fields=['top_genres', 'top_tags', 'last_interaction_at', 'updated_at'])
    return profile


def calculate_interest_match(post, profile):
    genre_score = profile.top_genres.get(post.genre, 0)
    tag_names = list(post.tags.values_list('name', flat=True))
    tag_score = (
        sum(profile.top_tags.get(tag_name, 0) for tag_name in tag_names) / len(tag_names)
        if tag_names else 0
    )
    return round((genre_score * 0.6) + (tag_score * 0.4), 4)


def calculate_freshness_score(post, now=None):
    now = now or timezone.now()
    age_hours = max((now - post.created_at).total_seconds() / 3600, 0)
    return round(math.exp(-age_hours / 48), 4)


def _bandit_ucb_score(user, genre, total_impressions):
    arm, _ = UserBanditArm.objects.get_or_create(
        user=user,
        arm_type=UserBanditArm.ARM_GENRE,
        arm_key=genre,
    )
    if arm.impressions == 0:
        return 10.0

    average_reward = arm.total_reward / max(arm.impressions, 1)
    exploration_bonus = UCB_EXPLORATION * math.sqrt(
        math.log(max(total_impressions, 2)) / arm.impressions
    )
    return average_reward + exploration_bonus


def _build_recent_penalties(user):
    cutoff = timezone.now() - timedelta(hours=RECENT_CATEGORY_WINDOW_HOURS)
    recent_impressions = list(
        FeedImpression.objects
        .filter(user=user, created_at__gte=cutoff)
        .select_related('post')
        .prefetch_related('post__tags')
    )
    category_counts = Counter(item.post.genre for item in recent_impressions)
    author_counts = Counter(item.post.author_id for item in recent_impressions)
    return category_counts, author_counts


def _apply_time_decay(user, post, base_score, profile):
    """Decay posts already shown, and downrank categories shown recently."""

    last_impression = (
        FeedImpression.objects
        .filter(user=user, post=post)
        .order_by('-created_at')
        .first()
    )
    if last_impression:
        hours_since = max((timezone.now() - last_impression.created_at).total_seconds() / 3600, 0)
        time_decay = math.exp(-profile.time_decay_lambda * hours_since)
    else:
        time_decay = 1.0

    category_counts, author_counts = _build_recent_penalties(user)
    category_penalty = 1 / (1 + 0.18 * category_counts.get(post.genre, 0))
    author_penalty = 1 / (1 + 0.12 * author_counts.get(post.author_id, 0))

    return round(base_score * time_decay * category_penalty * author_penalty, 4), {
        'time_decay_factor': round(time_decay, 4),
        'recent_category_penalty': round(category_penalty, 4),
        'recent_author_penalty': round(author_penalty, 4),
    }


def calculate_post_score(user, post, profile, recent_author_ids=None, recent_genres=None):
    analytics = getattr(post, 'analytics', None)
    engagement_score = analytics.engagement_score if analytics else 0
    interest_match = calculate_interest_match(post, profile)
    freshness_score = calculate_freshness_score(post)
    diversity_bonus = (
        (0.3 if post.author_id not in (recent_author_ids or set()) else -0.2)
        + (0.2 if post.genre not in (recent_genres or set()) else -0.1)
    )
    base_score = (
        0.35 * engagement_score
        + 0.40 * interest_match
        + 0.15 * freshness_score
        + 0.10 * diversity_bonus
    )
    final_score, decay_meta = _apply_time_decay(user, post, base_score, profile)
    return {
        'score': round(final_score, 4),
        'base_score': round(base_score, 4),
        'engagement_score': round(engagement_score, 4),
        'interest_match': round(interest_match, 4),
        'freshness_score': round(freshness_score, 4),
        'diversity_bonus': round(diversity_bonus, 4),
        **decay_meta,
    }


def _softmax_sample(posts, limit, score_attr='recommendation_score', temperature=SOFTMAX_TEMPERATURE):
    """Weighted random sampling so the highest score is not deterministic."""

    selected = []
    pool = list(posts)
    while pool and len(selected) < limit:
        max_score = max(getattr(item, score_attr, 0) for item in pool)
        weights = [
            math.exp((getattr(item, score_attr, 0) - max_score) / max(temperature, 0.01))
            for item in pool
        ]
        chosen = random.choices(pool, weights=weights, k=1)[0]
        selected.append(chosen)
        pool = [item for item in pool if item.id != chosen.id]
    return selected


def _viral_candidates(limit=10):
    now = timezone.now()
    return list(
        Post.objects
        .filter(viral_state__active=True)
        .filter(Q(viral_state__active_until__isnull=True) | Q(viral_state__active_until__gte=now))
        .select_related('author', 'analytics', 'distribution', 'viral_state')
        .prefetch_related('tags', 'comments', 'likes', 'bookmarks')
        .order_by('-viral_state__velocity_score')[:limit]
    )


def _build_exploration_candidates(user, scored_posts, profile):
    bandit_total = sum(
        UserBanditArm.objects.filter(user=user).values_list('impressions', flat=True)
    ) or 1

    candidates = []
    for post in scored_posts:
        if post.genre in profile.top_genres or any(tag.name in profile.top_tags for tag in post.tags.all()):
            continue
        sampled = _bandit_ucb_score(user, post.genre, bandit_total)
        post.exploration_score = round(post.recommendation_score + sampled * 0.12, 4)
        candidates.append(post)
    return _softmax_sample(sorted(candidates, key=lambda item: item.exploration_score, reverse=True), len(candidates), 'exploration_score')


def _bucket_targets(page_size, profile):
    exploration_ratio = min(max(profile.exploration_ratio, 0.2), 0.3)
    exploration_count = max(1, round(page_size * exploration_ratio))
    popular_count = max(1, round(page_size * FEED_BUCKET_WEIGHTS['popular']))
    wildcard_count = max(1, round(page_size * FEED_BUCKET_WEIGHTS['wildcard']))
    targeted_count = max(1, page_size - exploration_count - popular_count - wildcard_count)
    return {
        'targeted': targeted_count,
        'popular': popular_count,
        'exploration': exploration_count,
        'wildcard': wildcard_count,
    }


def _maximal_marginal_relevance(candidates, limit, user, profile):
    """Greedy session builder with author/category caps and novelty requirement."""

    selected = []
    author_counts = Counter()
    genre_counts = Counter()
    seen_authors = set(
        FeedImpression.objects.filter(user=user).values_list('post__author_id', flat=True)
    )
    needs_unseen_author = True

    while candidates and len(selected) < limit:
        best_candidate = None
        best_mmr = None

        for post in list(candidates):
            if author_counts[post.author_id] >= 2 or genre_counts[post.genre] >= 3:
                continue

            relevance = getattr(post, 'recommendation_score', 0)
            similarity_penalty = 0
            for existing in selected:
                if existing.author_id == post.author_id:
                    similarity_penalty += 0.9
                if existing.genre == post.genre:
                    similarity_penalty += 0.5
                existing_tags = set(existing.tags.values_list('name', flat=True))
                current_tags = set(post.tags.values_list('name', flat=True))
                if existing_tags and current_tags:
                    similarity_penalty += 0.25 * (len(existing_tags & current_tags) / len(existing_tags | current_tags))

            novelty_bonus = 0.4 if post.author_id not in seen_authors and needs_unseen_author else 0
            mmr_score = (MMR_LAMBDA * relevance) - ((1 - MMR_LAMBDA) * similarity_penalty) + novelty_bonus
            if best_candidate is None or mmr_score > best_mmr:
                best_candidate = post
                best_mmr = mmr_score

        if best_candidate is None:
            break

        selected.append(best_candidate)
        author_counts[best_candidate.author_id] += 1
        genre_counts[best_candidate.genre] += 1
        if best_candidate.author_id not in seen_authors:
            needs_unseen_author = False
        candidates = [item for item in candidates if item.id != best_candidate.id]

    if len(selected) < limit:
        remaining = [
            item for item in candidates
            if item.id not in {post.id for post in selected}
        ]
        remaining.sort(key=lambda item: getattr(item, 'recommendation_score', 0), reverse=True)
        for post in remaining:
            if len(selected) >= limit:
                break
            selected.append(post)

    return selected


def _record_impressions(user, posts, session_id):
    FeedImpression.objects.bulk_create([
        FeedImpression(
            user=user,
            post=post,
            session_id=session_id,
            bucket=getattr(post, 'recommendation_bucket', 'targeted'),
            rank_position=index + 1,
            base_score=getattr(post, 'recommendation_reasons', {}).get('base_score', 0),
            final_score=getattr(post, 'recommendation_score', 0),
        )
        for index, post in enumerate(posts)
    ])


def build_diverse_feed(user, page_size=10):
    """
    Core diversified feed builder:
    70% targeted, 15% popular, 10% exploration, 5% wildcard.
    Applies UCB exploration, softmax sampling, time decay and MMR.
    """

    # Avoid rebuilding and rewriting the full interest profile on every GET /feed
    # request. Interactions already refresh it during POST /interact, and SQLite
    # is very sensitive to concurrent writes.
    profile = ensure_user_interest_profile(user)
    recent_interactions = list(_recent_interactions_queryset(user)[:50])
    recent_author_ids = {item.post.author_id for item in recent_interactions}
    recent_genres = {item.post.genre for item in recent_interactions}
    seen_post_ids = {item.post_id for item in recent_interactions}

    global_queryset = (
        Post.objects
        .select_related('author', 'analytics', 'distribution', 'viral_state')
        .prefetch_related('tags', 'comments', 'likes', 'bookmarks')
        .prefetch_related(Prefetch('interactions'))
        .exclude(author=user)
    )
    assigned_post_ids = set(
        PostPoolRecipient.objects.filter(user=user).values_list('post_id', flat=True)
    )
    if assigned_post_ids:
        base_queryset = global_queryset.filter(id__in=assigned_post_ids)
    else:
        base_queryset = global_queryset

    candidates = list(base_queryset.order_by('-created_at')[:250])
    if not candidates:
        candidates = list(global_queryset.order_by('-created_at')[:250])

    scored_posts = []
    for post in candidates:
        score_details = calculate_post_score(
            user=user,
            post=post,
            profile=profile,
            recent_author_ids=recent_author_ids,
            recent_genres=recent_genres,
        )
        if post.id not in seen_post_ids:
            score_details['score'] = round(score_details['score'] + 0.05, 4)
            score_details['novelty_bonus'] = 0.05
        else:
            score_details['novelty_bonus'] = 0
        post.recommendation_score = score_details['score']
        post.recommendation_reasons = score_details
        scored_posts.append(post)

    targets = _bucket_targets(page_size, profile)

    targeted_pool = [
        post for post in scored_posts
        if post.genre in profile.top_genres
        or any(tag.name in profile.top_tags for tag in post.tags.all())
    ]
    popular_pool = sorted(
        scored_posts,
        key=lambda item: (
            getattr(getattr(item, 'analytics', None), 'engagement_score', 0),
            getattr(item, 'recommendation_score', 0),
        ),
        reverse=True,
    )
    exploration_pool = _build_exploration_candidates(user, scored_posts, profile)
    wildcard_pool = list(scored_posts)
    random.shuffle(wildcard_pool)

    viral_pool = _viral_candidates(limit=5)

    composed = []
    used_ids = set()

    def add_bucket(posts, limit, bucket_name):
        selected = _softmax_sample(posts, limit)
        for post in selected:
            if post.id in used_ids:
                continue
            post.recommendation_bucket = bucket_name
            composed.append(post)
            used_ids.add(post.id)

    add_bucket(sorted(targeted_pool, key=lambda item: item.recommendation_score, reverse=True), targets['targeted'], 'targeted')
    add_bucket(popular_pool, targets['popular'], 'popular')
    add_bucket(exploration_pool, targets['exploration'], 'exploration')
    add_bucket(wildcard_pool, targets['wildcard'], 'wildcard')

    if viral_pool:
        viral_post = next((post for post in viral_pool if post.id not in used_ids), None)
        if viral_post:
            viral_post.recommendation_bucket = 'viral'
            viral_post.recommendation_score = round(getattr(viral_post, 'recommendation_score', 0) + 0.2, 4)
            viral_post.recommendation_reasons = {
                **getattr(viral_post, 'recommendation_reasons', {}),
                'viral_velocity_score': getattr(getattr(viral_post, 'viral_state', None), 'velocity_score', 0),
            }
            composed.insert(min(2, len(composed)), viral_post)
            used_ids.add(viral_post.id)

    if len(composed) < page_size:
        filler = sorted(scored_posts, key=lambda item: item.recommendation_score, reverse=True)
        for post in filler:
            if post.id in used_ids:
                continue
            post.recommendation_bucket = getattr(post, 'recommendation_bucket', 'targeted')
            composed.append(post)
            used_ids.add(post.id)
            if len(composed) >= page_size * 2:
                break

    final_posts = _maximal_marginal_relevance(composed, page_size, user, profile)

    session_id = uuid.uuid4().hex
    try:
        _record_impressions(user, final_posts, session_id)
        profile.last_session_at = timezone.now()
        profile.save(update_fields=['last_session_at', 'updated_at'])
    except OperationalError:
        # The feed itself is still usable even if analytics/session bookkeeping
        # temporarily fails because SQLite is locked by another request.
        pass
    return final_posts


def get_diversified_feed(user_id, page_size=10):
    """Public entrypoint used by the /feed endpoint and background jobs."""

    user = User.objects.get(id=user_id)
    return build_diverse_feed(user, page_size=page_size)


def detect_viral_posts():
    """Hourly detector for posts with fast engagement growth."""

    now = timezone.now()
    current_window_start = now - timedelta(hours=1)
    previous_window_start = now - timedelta(hours=2)

    active_ids = set()
    for post in Post.objects.select_related('analytics').all():
        current_qs = PostInteraction.objects.filter(post=post, created_at__gte=current_window_start)
        previous_qs = PostInteraction.objects.filter(
            post=post,
            created_at__gte=previous_window_start,
            created_at__lt=current_window_start,
        )
        current_score = (
            current_qs.filter(signal=PostInteraction.SIGNAL_LIKE).count() * 1.5
            + current_qs.filter(signal=PostInteraction.SIGNAL_COMMENT).count() * 2
            + current_qs.filter(signal=PostInteraction.SIGNAL_SHARE).count() * 2.5
            + current_qs.filter(completed_read=True).count() * 1.2
        )
        previous_score = (
            previous_qs.filter(signal=PostInteraction.SIGNAL_LIKE).count() * 1.5
            + previous_qs.filter(signal=PostInteraction.SIGNAL_COMMENT).count() * 2
            + previous_qs.filter(signal=PostInteraction.SIGNAL_SHARE).count() * 2.5
            + previous_qs.filter(completed_read=True).count() * 1.2
        )

        growth = current_score - previous_score
        if current_score <= 0 or growth <= 0:
            continue

        velocity_score = growth + (getattr(post.analytics, 'engagement_score', 0) if hasattr(post, 'analytics') else 0)
        if velocity_score < 3:
            continue

        viral_state, _ = ViralPost.objects.update_or_create(
            post=post,
            defaults={
                'velocity_score': round(velocity_score, 4),
                'engagement_growth': round(growth, 4),
                'active': True,
                'active_until': now + timedelta(hours=VIRAL_ACTIVE_HOURS),
            },
        )
        active_ids.add(viral_state.post_id)

    ViralPost.objects.exclude(post_id__in=active_ids).update(active=False)
    return list(active_ids)


def evaluate_distribution_pools():
    """Hourly job that graduates posts through progressively larger pools."""

    now = timezone.now()
    moved_posts = []
    distributions = (
        PostDistribution.objects
        .select_related('post', 'post__analytics')
        .filter(status=PostDistribution.STATUS_ACTIVE)
    )

    for distribution in distributions:
        analytics = getattr(distribution.post, 'analytics', None)
        if not analytics:
            continue

        distribution.engagement_rate = compute_distribution_engagement_rate(analytics)
        threshold = POOL_THRESHOLDS.get(distribution.current_pool)

        if distribution.delivered_impressions == 0:
            assign_post_to_pool_users(
                distribution.post,
                pool_number=distribution.current_pool,
                target_size=distribution.current_pool_size,
            )

        if threshold is None:
            distribution.status = PostDistribution.STATUS_GRADUATED
        elif analytics.impressions >= distribution.current_pool_size and distribution.engagement_rate >= threshold:
            distribution.current_pool += 1
            distribution.current_pool_size = distribution.next_pool_size
            next_index = min(distribution.current_pool, len(POOL_SIZES) - 1)
            distribution.next_pool_size = POOL_SIZES[next_index]
            assign_post_to_pool_users(
                distribution.post,
                pool_number=distribution.current_pool,
                target_size=distribution.current_pool_size,
            )
            moved_posts.append(distribution.post_id)
        elif analytics.impressions >= distribution.current_pool_size:
            distribution.status = PostDistribution.STATUS_HOLD

        distribution.delivered_impressions = analytics.impressions
        distribution.last_evaluated_at = now
        distribution.save()

    return moved_posts


def bootstrap_post_recommendation_state(post):
    """Ensure every new post enters pool 1 and has analytics rows ready."""

    _get_or_create_analytics(post)
    distribution = _get_or_create_distribution(post)
    assign_post_to_pool_users(
        post,
        pool_number=distribution.current_pool,
        target_size=distribution.current_pool_size,
    )
    return post
