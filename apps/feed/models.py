from django.conf import settings
from django.db import models

from apps.posts.models import Post, Tag


class UserInterestProfile(models.Model):
    """Aggregated recommendation profile for one user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='interest_profile',
    )
    top_genres = models.JSONField(default=dict, blank=True)
    top_tags = models.JSONField(default=dict, blank=True)
    exploration_ratio = models.FloatField(default=0.10)
    time_decay_lambda = models.FloatField(default=0.08)
    last_session_at = models.DateTimeField(blank=True, null=True)
    last_interaction_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feed_user_interest_profile'

    def __str__(self):
        return f"Interest profile for {self.user.username}"


class UserGenreInterest(models.Model):
    """Per-genre affinity score for a user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='genre_interests',
    )
    genre = models.CharField(max_length=20)
    score = models.FloatField(default=0)
    interactions_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feed_user_genre_interest'
        unique_together = ('user', 'genre')
        indexes = [
            models.Index(fields=['user', '-score']),
            models.Index(fields=['genre', '-score']),
        ]

    def __str__(self):
        return f"{self.user.username} -> {self.genre} ({self.score:.2f})"


class UserTagInterest(models.Model):
    """Per-tag affinity score for a user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tag_interests',
    )
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='user_interests')
    score = models.FloatField(default=0)
    interactions_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feed_user_tag_interest'
        unique_together = ('user', 'tag')
        indexes = [
            models.Index(fields=['user', '-score']),
            models.Index(fields=['tag', '-score']),
        ]

    def __str__(self):
        return f"{self.user.username} -> {self.tag.name} ({self.score:.2f})"


class UserBanditArm(models.Model):
    """Per-user statistics for exploration/exploitation balancing."""

    ARM_GENRE = 'genre'
    ARM_TAG = 'tag'
    ARM_WILDCARD = 'wildcard'

    ARM_TYPE_CHOICES = [
        (ARM_GENRE, 'Genre'),
        (ARM_TAG, 'Tag'),
        (ARM_WILDCARD, 'Wildcard'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bandit_arms',
    )
    arm_type = models.CharField(max_length=20, choices=ARM_TYPE_CHOICES)
    arm_key = models.CharField(max_length=100)
    impressions = models.PositiveIntegerField(default=0)
    successes = models.PositiveIntegerField(default=0)
    failures = models.PositiveIntegerField(default=0)
    total_reward = models.FloatField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feed_user_bandit_arm'
        unique_together = ('user', 'arm_type', 'arm_key')
        indexes = [
            models.Index(fields=['user', 'arm_type']),
            models.Index(fields=['user', '-updated_at']),
        ]

    def __str__(self):
        return f"{self.user.username} {self.arm_type}:{self.arm_key}"


class PostInteraction(models.Model):
    """Stores user engagement signals for each post impression or action."""

    SIGNAL_VIEW = 'view'
    SIGNAL_SCROLL = 'scroll'
    SIGNAL_LIKE = 'like'
    SIGNAL_COMMENT = 'comment'
    SIGNAL_SHARE = 'share'
    SIGNAL_BOOKMARK = 'bookmark'
    SIGNAL_REPORT = 'report'

    SIGNAL_CHOICES = [
        (SIGNAL_VIEW, 'View'),
        (SIGNAL_SCROLL, 'Scroll'),
        (SIGNAL_LIKE, 'Like'),
        (SIGNAL_COMMENT, 'Comment'),
        (SIGNAL_SHARE, 'Share'),
        (SIGNAL_BOOKMARK, 'Bookmark'),
        (SIGNAL_REPORT, 'Report'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='post_interactions',
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='interactions')
    signal = models.CharField(max_length=20, choices=SIGNAL_CHOICES)
    reading_time_ms = models.PositiveIntegerField(default=0)
    read_progress = models.FloatField(default=0)
    completed_read = models.BooleanField(default=False)
    reread_count = models.PositiveIntegerField(default=0)
    is_quick_scroll = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'feed_post_interaction'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['post', '-created_at']),
            models.Index(fields=['signal', '-created_at']),
            models.Index(fields=['user', 'post', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} {self.signal} post {self.post_id}"


class FeedImpression(models.Model):
    """Tracks when a post was shown inside a feed session."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feed_impressions',
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='feed_impressions')
    session_id = models.CharField(max_length=64, blank=True, default='')
    bucket = models.CharField(max_length=30, default='targeted')
    rank_position = models.PositiveIntegerField(default=0)
    base_score = models.FloatField(default=0)
    final_score = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'feed_impression'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['post', '-created_at']),
            models.Index(fields=['user', 'bucket', '-created_at']),
        ]

    def __str__(self):
        return f"Impression user={self.user_id} post={self.post_id}"


class PostAnalytics(models.Model):
    """Denormalized counters used by the scoring engine."""

    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name='analytics')
    impressions = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)
    unique_viewers = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    comments = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    bookmarks = models.PositiveIntegerField(default=0)
    reports = models.PositiveIntegerField(default=0)
    complete_reads = models.PositiveIntegerField(default=0)
    rereads = models.PositiveIntegerField(default=0)
    quick_scrolls = models.PositiveIntegerField(default=0)
    total_reading_time_ms = models.PositiveBigIntegerField(default=0)
    avg_read_progress = models.FloatField(default=0)
    engagement_score = models.FloatField(default=0)
    last_engagement_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feed_post_analytics'
        indexes = [
            models.Index(fields=['-engagement_score']),
            models.Index(fields=['-updated_at']),
        ]

    def __str__(self):
        return f"Analytics for post {self.post_id}"


class PostDistribution(models.Model):
    """Controls pool-based propagation inspired by TikTok staged diffusion."""

    STATUS_ACTIVE = 'active'
    STATUS_HOLD = 'hold'
    STATUS_GRADUATED = 'graduated'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_HOLD, 'Hold'),
        (STATUS_GRADUATED, 'Graduated'),
    ]

    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name='distribution')
    current_pool = models.PositiveIntegerField(default=1)
    current_pool_size = models.PositiveIntegerField(default=500)
    next_pool_size = models.PositiveIntegerField(default=5000)
    last_evaluated_at = models.DateTimeField(blank=True, null=True)
    engagement_rate = models.FloatField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    delivered_impressions = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feed_post_distribution'
        indexes = [
            models.Index(fields=['status', 'current_pool']),
            models.Index(fields=['-updated_at']),
        ]

    def __str__(self):
        return f"Distribution for post {self.post_id} - pool {self.current_pool}"


class PostPoolRecipient(models.Model):
    """Users selected to receive a post during a specific distribution pool."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='pool_recipients')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recommended_pool_posts',
    )
    pool_number = models.PositiveIntegerField()
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'feed_post_pool_recipient'
        unique_together = ('post', 'user', 'pool_number')
        indexes = [
            models.Index(fields=['user', 'pool_number']),
            models.Index(fields=['post', 'pool_number']),
        ]

    def __str__(self):
        return f"Post {self.post_id} -> {self.user.username} (pool {self.pool_number})"


class ViralPost(models.Model):
    """Stores temporarily boosted posts detected by the hourly viral job."""

    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name='viral_state')
    velocity_score = models.FloatField(default=0)
    engagement_growth = models.FloatField(default=0)
    active = models.BooleanField(default=True)
    detected_at = models.DateTimeField(auto_now_add=True)
    active_until = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feed_viral_post'
        indexes = [
            models.Index(fields=['active', '-velocity_score']),
            models.Index(fields=['-updated_at']),
        ]

    def __str__(self):
        return f"Viral post {self.post_id} ({self.velocity_score:.2f})"
