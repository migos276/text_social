import json

from rest_framework import serializers
from apps.posts.models import Post, Like, Comment, Bookmark, Tag
from apps.users.serializers import UserProfileSerializer


DEFAULT_POST_BACKGROUND = '#1A1A1A'
MAX_AUDIO_FILE_SIZE = 10 * 1024 * 1024
MAX_AUDIO_DURATION_MS = 10 * 60 * 1000


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name']
        read_only_fields = ['id']


class TagListField(serializers.Field):
    """Accepts raw tag names and returns them as a normalized list."""

    def to_representation(self, value):
        return list(value.values_list('name', flat=True))

    def to_internal_value(self, data):
        if data in (None, ''):
            return []
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError('tags must be a list of strings.') from exc
        if not isinstance(data, list):
            raise serializers.ValidationError('tags must be a list of strings.')

        normalized = []
        for item in data:
            item = str(item).strip().lower()
            if not item:
                continue
            normalized.append(item[:50])
        return list(dict.fromkeys(normalized))


class CommentSerializer(serializers.ModelSerializer):
    author = UserProfileSerializer(read_only=True)
    author_id = serializers.IntegerField(write_only=True, required=False)
    post = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Comment
        fields = ['id', 'author', 'author_id', 'post', 'content', 'created_at', 'updated_at']
        read_only_fields = ['id', 'author', 'post', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class LikeSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = Like
        fields = ['id', 'user', 'post', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class BookmarkSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)

    class Meta:
        model = Bookmark
        fields = ['id', 'user', 'post', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class PostSerializer(serializers.ModelSerializer):
    author = UserProfileSerializer(read_only=True)
    author_id = serializers.IntegerField(write_only=True, required=False)
    tags = TagListField(required=False)
    likes_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    user_has_liked = serializers.SerializerMethodField()
    bookmarks_count = serializers.SerializerMethodField()
    user_has_bookmarked = serializers.SerializerMethodField()
    comments = CommentSerializer(many=True, read_only=True)
    recommendation_score = serializers.FloatField(read_only=True)
    recommendation_reasons = serializers.JSONField(read_only=True)
    recommendation_bucket = serializers.CharField(read_only=True)
    audio_file = serializers.FileField(write_only=True, required=False, allow_null=True)
    audio_url = serializers.SerializerMethodField()
    background_color = serializers.RegexField(
        regex=r'^#[0-9A-Fa-f]{6}$',
        required=False,
        default=DEFAULT_POST_BACKGROUND,
    )
    
    class Meta:
        model = Post
        fields = [
            'id',
            'author',
            'author_id',
            'content',
            'genre',
            'background_color',
            'audio_file',
            'audio_url',
            'audio_title',
            'audio_duration_ms',
            'tags',
            'created_at',
            'updated_at',
            'likes_count',
            'comments_count',
            'user_has_liked',
            'bookmarks_count',
            'user_has_bookmarked',
            'comments',
            'recommendation_score',
            'recommendation_reasons',
            'recommendation_bucket',
        ]
        read_only_fields = ['id', 'author', 'created_at', 'updated_at', 'likes_count', 'comments_count', 'user_has_liked', 'bookmarks_count', 'user_has_bookmarked']

    def get_audio_url(self, obj):
        request = self.context.get('request')
        if not obj.audio_file:
            return None
        url = obj.audio_file.url
        return request.build_absolute_uri(url) if request else url

    def validate_audio_file(self, value):
        if not value:
            return value
        if getattr(value, 'size', 0) > MAX_AUDIO_FILE_SIZE:
            raise serializers.ValidationError('Le fichier audio ne doit pas depasser 10 Mo.')
        return value

    def validate_audio_duration_ms(self, value):
        value = int(value or 0)
        if value < 0:
            raise serializers.ValidationError('La duree audio est invalide.')
        if value > MAX_AUDIO_DURATION_MS:
            raise serializers.ValidationError('La duree audio ne doit pas depasser 10 minutes.')
        return value
    
    def get_likes_count(self, obj):
        return obj.likes.count()
    
    def get_comments_count(self, obj):
        return obj.comments.count()
    
    def get_user_has_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False

    def get_bookmarks_count(self, obj):
        return obj.bookmarks.count()

    def get_user_has_bookmarked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.bookmarks.filter(user=request.user).exists()
        return False
    
    def create(self, validated_data):
        tags = validated_data.pop('tags', [])
        validated_data['author'] = self.context['request'].user
        post = super().create(validated_data)
        if tags:
            post.tags.set([Tag.objects.get_or_create(name=tag_name)[0] for tag_name in tags])
        return post

    def update(self, instance, validated_data):
        tags = validated_data.pop('tags', None)
        instance = super().update(instance, validated_data)
        if tags is not None:
            instance.tags.set([Tag.objects.get_or_create(name=tag_name)[0] for tag_name in tags])
        return instance


class PostDetailSerializer(serializers.ModelSerializer):
    author = UserProfileSerializer(read_only=True)
    author_id = serializers.IntegerField(write_only=True, required=False)
    tags = TagSerializer(many=True, read_only=True)
    likes_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    user_has_liked = serializers.SerializerMethodField()
    bookmarks_count = serializers.SerializerMethodField()
    user_has_bookmarked = serializers.SerializerMethodField()
    comments = CommentSerializer(many=True, read_only=True)
    likes = LikeSerializer(many=True, read_only=True)
    bookmarks = BookmarkSerializer(many=True, read_only=True)
    audio_url = serializers.SerializerMethodField()
    background_color = serializers.RegexField(
        regex=r'^#[0-9A-Fa-f]{6}$',
        read_only=True,
    )
    
    class Meta:
        model = Post
        fields = [
            'id',
            'author',
            'author_id',
            'content',
            'genre',
            'background_color',
            'audio_url',
            'audio_title',
            'audio_duration_ms',
            'tags',
            'created_at',
            'updated_at',
            'likes_count',
            'comments_count',
            'user_has_liked',
            'bookmarks_count',
            'user_has_bookmarked',
            'comments',
            'likes',
            'bookmarks'
        ]
        read_only_fields = [
            'id',
            'author',
            'created_at',
            'updated_at',
            'likes_count',
            'comments_count',
            'user_has_liked',
            'bookmarks_count',
            'user_has_bookmarked',
            'comments',
            'likes',
            'bookmarks'
        ]

    def get_audio_url(self, obj):
        request = self.context.get('request')
        if not obj.audio_file:
            return None
        url = obj.audio_file.url
        return request.build_absolute_uri(url) if request else url
    
    def get_likes_count(self, obj):
        return obj.likes.count()
    
    def get_comments_count(self, obj):
        return obj.comments.count()
    
    def get_user_has_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False

    def get_bookmarks_count(self, obj):
        return obj.bookmarks.count()

    def get_user_has_bookmarked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.bookmarks.filter(user=request.user).exists()
        return False
