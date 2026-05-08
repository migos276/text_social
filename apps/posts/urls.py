from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.posts.views import PostViewSet, CommentViewSet

router = DefaultRouter()
router.register(r'', PostViewSet, basename='post')
router.register(r'comments', CommentViewSet, basename='comment')

urlpatterns = [
    path('', include(router.urls)),
]
