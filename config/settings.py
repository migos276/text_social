"""
Django settings for TEXT backend project.
"""

import os
from pathlib import Path
from datetime import timedelta

try:
    from decouple import config
except ImportError:
    def config(name, default=None, cast=str):
        value = os.environ.get(name, default)
        if cast is bool:
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}
        if cast is None:
            return value
        return cast(value)


def get_bool_config(name, default=False):
    value = os.environ.get(name)
    if value is None:
        try:
            return config(name, default=default, cast=bool)
        except Exception:
            return default

    normalized = str(value).strip().lower()
    if normalized in {'1', 'true', 'yes', 'on', 'debug', 'dev', 'development'}:
        return True
    if normalized in {'0', 'false', 'no', 'off', 'release', 'prod', 'production'}:
        return False
    return default


def get_list_config(name, default=''):
    raw_value = os.environ.get(name, default)
    if raw_value is None:
        return []
    return [item.strip() for item in str(raw_value).split(',') if item.strip()]

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-this-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = get_bool_config('DEBUG', default=True)
BACKEND_DOMAIN = config('BACKEND_DOMAIN', default='text.tfs237.com')
BACKEND_ORIGIN = config('BACKEND_ORIGIN', default=f'https://{BACKEND_DOMAIN}')
FRONTEND_URLS = get_list_config(
    'FRONTEND_URLS',
    default='http://localhost:3000,http://localhost:8081,http://127.0.0.1:3000',
)

# En developpement on accepte toutes les connexions pour les tests reseau mobile.
ALLOWED_HOSTS = ['*'] if DEBUG else get_list_config(
    'ALLOWED_HOSTS',
    default=f'{BACKEND_DOMAIN},localhost,127.0.0.1',
)

# Application definition
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'corsheaders',
    'rest_framework_simplejwt',

    'apps.users',
    'apps.posts',
    'apps.feed',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,
        },
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'users.CustomUser'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_FILTER_BACKENDS': (
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
}

# JWT Configuration
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ALGORITHM': 'HS256',
}

# CORS Configuration
# En production, indique les URLs exactes de ton front:
# FRONTEND_URLS=https://ton-front.com,https://www.ton-front.com
# CORS_ALLOWED_ORIGINS permet aussi d'ajouter des origines supplementaires si besoin.
DEFAULT_DEV_CORS_ORIGINS = [
    'http://172.20.10.3:8000',
    'http://172.20.10.3:8081',
    'http://172.20.10.3:19000',
    'http://172.20.10.3:19006',
    'http://localhost:3000',
    'http://localhost:8000',
    'http://127.0.0.1:3000',
    'http://127.0.0.1:8000',
]

extra_cors_origins = get_list_config('CORS_ALLOWED_ORIGINS', default='')
CORS_ALLOWED_ORIGINS = list(
    dict.fromkeys(
        (
            DEFAULT_DEV_CORS_ORIGINS if DEBUG else []
        ) + FRONTEND_URLS + extra_cors_origins + [BACKEND_ORIGIN]
    )
)

# En developpement, on laisse passer les requetes du telephone sans bloquer sur CORS.
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(
        get_list_config('CSRF_TRUSTED_ORIGINS', default='') + FRONTEND_URLS + [BACKEND_ORIGIN]
    )
)

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = get_bool_config('SECURE_SSL_REDIRECT', default=False)
