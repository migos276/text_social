from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.posts.models import Post, Like, Comment, Bookmark
from apps.posts.serializers import PostSerializer, PostDetailSerializer, CommentSerializer, LikeSerializer, BookmarkSerializer
from apps.users.permissions import IsOwnerOrReadOnly
from apps.feed.serializers import PostInteractionSerializer
from apps.feed.models import PostInteraction
from apps.feed.services import bootstrap_post_recommendation_state, record_post_interaction


class PostViewSet(viewsets.ModelViewSet):
    """ViewSet for posts"""
    queryset = Post.objects.select_related('author').prefetch_related('likes', 'comments', 'bookmarks', 'tags')
    lookup_field = 'id'
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['content', 'author__username', 'genre']
    ordering_fields = ['created_at', 'likes_count']
    ordering = ['-created_at']
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PostDetailSerializer
        return PostSerializer
    
    def get_permissions(self):
        if self.action in ['create']:
            permission_classes = [IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [IsOwnerOrReadOnly, IsAuthenticated]
        else:
            permission_classes = [AllowAny]
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        post = serializer.save(author=self.request.user)
        bootstrap_post_recommendation_state(post)
    
    def perform_update(self, serializer):
        serializer.save()
    
    def perform_destroy(self, instance):
        if instance.author != self.request.user:
            raise PermissionError("You can only delete your own posts.")
        instance.delete()
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def like(self, request, id=None):
        """Like or unlike a post"""
        post = self.get_object()
        like, created = Like.objects.get_or_create(user=request.user, post=post)
        
        if not created:
            like.delete()
            return Response(
                {'message': 'Post unliked', 'liked': False},
                status=status.HTTP_200_OK
            )

        record_post_interaction(
            request.user,
            post,
            signal=PostInteraction.SIGNAL_LIKE,
            completed_read=False,
        )
        
        return Response(
            {'message': 'Post liked', 'liked': True},
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['get'])
    def comments(self, request, id=None):
        """Get comments for a post"""
        post = self.get_object()
        comments = post.comments.all()
        
        paginator = self.paginator
        page = paginator.paginate_queryset(comments, request)
        if page is not None:
            serializer = CommentSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
        
        serializer = CommentSerializer(comments, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def add_comment(self, request, id=None):
        """Add a comment to a post"""
        post = self.get_object()
        serializer = CommentSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            serializer.save(author=request.user, post=post)
            record_post_interaction(
                request.user,
                post,
                signal=PostInteraction.SIGNAL_COMMENT,
                completed_read=True,
                read_progress=1,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def likes(self, request, id=None):
        """Get users who liked a post"""
        post = self.get_object()
        likes = post.likes.all()
        
        paginator = self.paginator
        page = paginator.paginate_queryset(likes, request)
        if page is not None:
            serializer = LikeSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
        
        serializer = LikeSerializer(likes, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def bookmark(self, request, id=None):
        """Bookmark or remove a bookmarked post"""
        post = self.get_object()
        bookmark, created = Bookmark.objects.get_or_create(user=request.user, post=post)

        if not created:
            bookmark.delete()
            return Response(
                {'message': 'Post removed from favorites', 'bookmarked': False},
                status=status.HTTP_200_OK
            )

        record_post_interaction(
            request.user,
            post,
            signal=PostInteraction.SIGNAL_BOOKMARK,
            completed_read=True,
            read_progress=1,
        )

        return Response(
            {'message': 'Post added to favorites', 'bookmarked': True},
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['get'])
    def bookmarks(self, request, id=None):
        """Get users who bookmarked a post"""
        post = self.get_object()
        bookmarks = post.bookmarks.all()

        paginator = self.paginator
        page = paginator.paginate_queryset(bookmarks, request)
        if page is not None:
            serializer = BookmarkSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)

        serializer = BookmarkSerializer(bookmarks, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def interact(self, request, id=None):
        """Track reading, scroll and explicit engagement events for recommendation."""
        post = self.get_object()
        serializer = PostInteractionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        interaction = record_post_interaction(
            request.user,
            post,
            signal=serializer.validated_data['signal'],
            reading_time_ms=serializer.validated_data.get('reading_time_ms', 0),
            read_progress=serializer.validated_data.get('read_progress', 0),
            completed_read=serializer.validated_data.get('completed_read', False),
            reread_count=serializer.validated_data.get('reread_count', 0),
            is_quick_scroll=serializer.validated_data.get('is_quick_scroll', False),
            metadata=serializer.validated_data.get('metadata', {}),
        )
        return Response(
            {
                'message': 'Interaction tracked',
                'interaction_id': interaction.id,
            },
            status=status.HTTP_201_CREATED,
        )


class CommentViewSet(viewsets.ModelViewSet):
    """ViewSet for comments"""
    queryset = Comment.objects.select_related('author', 'post')
    serializer_class = CommentSerializer
    permission_classes = [IsOwnerOrReadOnly, IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create']:
            permission_classes = [IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [IsOwnerOrReadOnly, IsAuthenticated]
        else:
            permission_classes = [AllowAny]
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
    
    def perform_destroy(self, instance):
        if instance.author != self.request.user:
            raise PermissionError("You can only delete your own comments.")
        instance.delete()
