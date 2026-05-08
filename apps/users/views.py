from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.users.models import Follow
from apps.users.serializers import (
    UserRegistrationSerializer,
    UserProfileSerializer,
    UserDetailSerializer,
    FollowSerializer
)
from apps.users.permissions import IsOwnerOrReadOnly

User = get_user_model()


def build_auth_payload(user, token_data=None, request=None):
    payload = {}
    if token_data:
        payload.update(token_data)
    payload['user'] = UserProfileSerializer(user, context={'request': request}).data
    return payload


class AuthViewSet(viewsets.ViewSet):
    """ViewSet for user authentication"""
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    
    @action(detail=False, methods=['post'])
    def register(self, request):
        """Register a new user"""
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                build_auth_payload(user, request=request),
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def login(self, request):
        """Login user (returns JWT tokens)"""
        login_value = request.data.get('username') or request.data.get('email') or request.data.get('login')
        password = request.data.get('password')

        if not login_value or not password:
            return Response(
                {'detail': 'Username/email and password are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        lookup_kwargs = {'email__iexact': login_value} if '@' in str(login_value) else {'username': login_value}
        user = User.objects.filter(**lookup_kwargs).first()
        username = user.username if user else login_value

        serializer = TokenObtainPairSerializer(data={'username': username, 'password': password})
        if serializer.is_valid():
            authenticated_user = User.objects.filter(username=username).first()
            return Response(
                build_auth_payload(authenticated_user, serializer.validated_data, request),
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """Logout user"""
        return Response(
            {'message': 'Logged out successfully'},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get', 'patch'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Read or update the authenticated user profile."""
        if request.method.lower() == 'get':
            return Response(UserProfileSerializer(request.user, context={'request': request}).data)

        serializer = UserDetailSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class UserViewSet(viewsets.ModelViewSet):
    """ViewSet for user profiles"""
    queryset = User.objects.all()
    lookup_field = 'username'
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    search_fields = ['username', 'bio', 'email']
    ordering_fields = ['username', 'date_joined']
    ordering = ['username']
    
    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return UserProfileSerializer
        elif self.action in ['update', 'partial_update']:
            return UserDetailSerializer
        return UserProfileSerializer
    
    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [IsOwnerOrReadOnly]
        else:
            permission_classes = [AllowAny]
        return [permission() for permission in permission_classes]
    
    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        filter_kwargs = {self.lookup_field: self.kwargs[self.lookup_field]}
        obj = get_object_or_404(queryset, **filter_kwargs)
        self.check_object_permissions(self.request, obj)
        return obj
    
    @action(detail=True, methods=['get'])
    def posts(self, request, username=None):
        """Get all posts by a user"""
        user = self.get_object()
        posts = user.posts.all().order_by('-created_at')
        
        paginator = self.paginator
        page = paginator.paginate_queryset(posts, request)
        if page is not None:
            from apps.posts.serializers import PostSerializer
            serializer = PostSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
        
        from apps.posts.serializers import PostSerializer
        serializer = PostSerializer(posts, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def follow(self, request, username=None):
        """Follow or unfollow a user"""
        user_to_follow = self.get_object()
        
        if request.user == user_to_follow:
            return Response(
                {'error': 'You cannot follow yourself'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        follow, created = Follow.objects.get_or_create(
            follower=request.user,
            following=user_to_follow
        )
        
        if not created:
            follow.delete()
            return Response(
                {'message': 'Unfollowed successfully'},
                status=status.HTTP_200_OK
            )
        
        return Response(
            {'message': 'Followed successfully'},
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['get'])
    def followers(self, request, username=None):
        """Get list of followers"""
        user = self.get_object()
        followers = user.followers_set.all()
        
        paginator = self.paginator
        page = paginator.paginate_queryset(followers, request)
        if page is not None:
            serializer = FollowSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
        
        serializer = FollowSerializer(followers, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def following(self, request, username=None):
        """Get list of users being followed"""
        user = self.get_object()
        following = user.following_set.all()
        
        paginator = self.paginator
        page = paginator.paginate_queryset(following, request)
        if page is not None:
            serializer = FollowSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
        
        serializer = FollowSerializer(following, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get', 'patch'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Read or update the authenticated user profile"""
        if request.method.lower() == 'get':
            serializer = UserProfileSerializer(request.user, context={'request': request})
            return Response(serializer.data)

        serializer = UserDetailSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
