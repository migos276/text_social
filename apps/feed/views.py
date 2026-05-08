from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.posts.serializers import PostSerializer
from apps.feed.serializers import UserInterestProfileSerializer
from apps.feed.services import ensure_user_interest_profile, get_diversified_feed


class FeedPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 30


class FeedViewSet(viewsets.ViewSet):
    """ViewSet for personalized feed"""
    permission_classes = [IsAuthenticated]
    pagination_class = FeedPagination
    
    def list(self, request):
        paginator = self.pagination_class()
        page_size = paginator.get_page_size(request) or paginator.page_size
        try:
            current_page = max(int(request.query_params.get('page', 1)), 1)
        except (TypeError, ValueError):
            current_page = 1
        posts = get_diversified_feed(request.user.id, page_size=page_size * current_page * 3)
        page = paginator.paginate_queryset(posts, request, view=self)
        serializer = PostSerializer(page, many=True, context={'request': request})
        response = paginator.get_paginated_response(serializer.data)
        response.data['composition'] = {
            'targeted': '70%',
            'popular': '15%',
            'exploration': '10%',
            'wildcard': '5%',
            'viral_injection': '1 boosted post when available',
        }
        return response

    @action(detail=False, methods=['get'])
    def profile(self, request):
        """Expose the live recommendation profile for debugging and tuning."""
        profile = ensure_user_interest_profile(request.user)
        serializer = UserInterestProfileSerializer(profile)
        return Response(serializer.data)
