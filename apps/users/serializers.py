from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.users.models import Follow

User = get_user_model()
MAX_AVATAR_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp"}


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password2 = serializers.CharField(write_only=True, min_length=6)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2']
    
    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "Passwords must match."})
        return data
    
    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    posts_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'bio',
            'avatar',
            'date_joined',
            'followers_count',
            'following_count',
            'posts_count',
            'is_following'
        ]
    
    def get_followers_count(self, obj):
        return obj.followers_set.count()
    
    def get_following_count(self, obj):
        return obj.following_set.count()
    
    def get_posts_count(self, obj):
        return obj.posts.count()
    
    def get_is_following(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Follow.objects.filter(
                follower=request.user,
                following=obj
            ).exists()
        return False

    def get_avatar(self, obj):
        if not obj.avatar:
            return None

        request = self.context.get('request')
        avatar_url = obj.avatar.url
        return request.build_absolute_uri(avatar_url) if request else avatar_url


class UserDetailSerializer(serializers.ModelSerializer):
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    posts_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField(read_only=True)
    avatar_file = serializers.ImageField(write_only=True, required=False, allow_null=True, source='avatar')
    
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'bio',
            'avatar',
            'avatar_file',
            'date_joined',
            'followers_count',
            'following_count',
            'posts_count',
            'is_following'
        ]
        read_only_fields = ['id', 'date_joined', 'followers_count', 'following_count', 'posts_count', 'is_following']
    
    def get_followers_count(self, obj):
        return obj.followers_set.count()
    
    def get_following_count(self, obj):
        return obj.following_set.count()
    
    def get_posts_count(self, obj):
        return obj.posts.count()
    
    def get_is_following(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Follow.objects.filter(
                follower=request.user,
                following=obj
            ).exists()
        return False

    def get_avatar(self, obj):
        if not obj.avatar:
            return None

        request = self.context.get('request')
        avatar_url = obj.avatar.url
        return request.build_absolute_uri(avatar_url) if request else avatar_url

    def validate_avatar_file(self, value):
        content_type = getattr(value, 'content_type', '')
        if content_type and content_type not in ALLOWED_AVATAR_TYPES:
            raise serializers.ValidationError(
                "La photo de profil doit etre au format JPG, PNG ou WEBP."
            )

        if value.size > MAX_AVATAR_FILE_SIZE:
            raise serializers.ValidationError(
                "La photo de profil ne doit pas depasser 5 Mo."
            )

        return value

    def update(self, instance, validated_data):
        previous_avatar = instance.avatar if instance.avatar else None
        updated_user = super().update(instance, validated_data)

        if previous_avatar and updated_user.avatar and previous_avatar.name != updated_user.avatar.name:
            previous_avatar.delete(save=False)

        return updated_user


class FollowSerializer(serializers.ModelSerializer):
    follower = UserProfileSerializer(read_only=True)
    following = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = Follow
        fields = ['id', 'follower', 'following', 'created_at']
        read_only_fields = ['created_at']
