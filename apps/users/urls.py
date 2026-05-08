from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.views import AuthViewSet, UserViewSet

router = DefaultRouter()
router.register(r'', UserViewSet, basename='user')

urlpatterns = [
    # Auth endpoints
    path('register/', AuthViewSet.as_view({'post': 'register'}), name='auth-register'),
    path('login/', AuthViewSet.as_view({'post': 'login'}), name='token_obtain_pair'),
    path('logout/', AuthViewSet.as_view({'post': 'logout'}), name='auth-logout'),
    path('me/', AuthViewSet.as_view({'get': 'me', 'patch': 'me'}), name='auth-me'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('user-me/', UserViewSet.as_view({'get': 'me', 'patch': 'me'}), name='user-me'),
    
    # User endpoints
    path('', include(router.urls)),
]
