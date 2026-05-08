from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.feed.views import FeedViewSet

router = DefaultRouter()
router.register(r'', FeedViewSet, basename='feed')

urlpatterns = [
    path('', include(router.urls)),
]
