from rest_framework import serializers

from apps.feed.models import PostInteraction, UserInterestProfile


class PostInteractionSerializer(serializers.ModelSerializer):
    """Accepts user engagement events from the client."""

    class Meta:
        model = PostInteraction
        fields = [
            'signal',
            'reading_time_ms',
            'read_progress',
            'completed_read',
            'reread_count',
            'is_quick_scroll',
            'metadata',
        ]

    def validate_read_progress(self, value):
        if value < 0 or value > 1:
            raise serializers.ValidationError('read_progress must be between 0 and 1.')
        return value


class UserInterestProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInterestProfile
        fields = [
            'top_genres',
            'top_tags',
            'exploration_ratio',
            'time_decay_lambda',
            'last_session_at',
            'last_interaction_at',
            'updated_at',
        ]
        read_only_fields = fields
