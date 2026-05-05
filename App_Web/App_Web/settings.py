"""
Django settings for bite_co project.

En AWS (Fargate + ALB) defina variables de entorno; ver docs/DESPLIEGUE_AWS.md.
"""

import os
from pathlib import Path

import environ

# Setup environ
env = environ.Env(
    DJANGO_DEBUG=(bool, True),
    DJANGO_ALLOWED_HOSTS=(list, ["*"]),
)

BASE_DIR = Path(__file__).resolve().parent.parent

# Read .env file if it exists
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

_DEFAULT_SECRET = "django-insecure-#77&k++v*!p=ax@w(t083zq=4#)1ds(-k@taoehf7tgy01-36x"
SECRET_KEY = env("DJANGO_SECRET_KEY", default=_DEFAULT_SECRET)

# IMPORTANTE: DEBUG debe ser False en producción (AWS)
DEBUG = env("DJANGO_DEBUG")

ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'core',
]

AUTH_USER_MODEL = 'core.Usuario'

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "core.auth0_utils.Auth0JSONWebTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# Simular rechazo por cola alta al generar reportes (notificación por correo en modelo Notificacion).
BITE_SIMULAR_SOBRECARGA_REPORTES = False

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'App_Web.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'App_Web.wsgi.application'


# Database
# Local: lee DATABASE_URL del archivo .env. AWS: lee DATABASE_URL del entorno de ECS/Fargate.
DATABASES = {
    'default': env.db('DATABASE_URL', default='sqlite:///db.sqlite3')
}

# Cache config (Redis/ElastiCache)
# - Producción (AWS Cluster Mode Enabled): Usar REDIS_URL=rediss://host:6379
# - Local / Standalone: Usar REDIS_URL=redis://host:6379/1
if env("REDIS_URL", default=None):
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": env("REDIS_URL"),
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "CONNECTION_POOL_KWARGS": {
                    "max_connections": 100,
                    "retry_on_timeout": True,
                    "ssl_cert_reqs": None,  # Necesario para ElastiCache con TLS
                },
                # Forzar fallo rápido (en 2 seg) si Redis no responde
                "SOCKET_TIMEOUT": 5,
                "SOCKET_CONNECT_TIMEOUT": 5,
                "IGNORE_EXCEPTIONS": False,  # False para ver el error real en logs/browser
            },
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-snowflake",
        }
    }

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'es-co'

TIME_ZONE = 'America/Bogota'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- SEGURIDAD Y CORS ---
CORS_ALLOW_ALL_ORIGINS = True  # Ajustar en producción real a dominios específicos

# Forzar HTTPS si estamos en producción (DEBUG=False)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# --- CONFIGURACIÓN AUTH0 ---
AUTH0_DOMAIN = env("AUTH0_DOMAIN", default="dev-example.auth0.com")
AUTH0_API_AUDIENCE = env("AUTH0_API_AUDIENCE", default="https://bite-co/api")
AUTH0_CLIENT_ID = env("AUTH0_CLIENT_ID", default="")
AUTH0_CLIENT_SECRET = env("AUTH0_CLIENT_SECRET", default="")

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'core.auth0_utils.Auth0JSONWebTokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
}

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]
