"""
Django settings for playsmear project.

Generated by 'django-admin startproject' using Django 2.0.2.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.0/ref/settings/
"""

import os
from datetime import timedelta

from api.logging import add_game_id_filter

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "amazing, I have the same key on my luggage")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    "api",
    "localhost",
    "0.0.0.0",
    "playsmear.fly.dev",
    "testplaysmear.fly.dev",
    "test.playsmear.com",
    "playsmear.com",
    "www.playsmear.com",
]

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_jwt.authentication.JSONWebTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ),
    "EXCEPTION_HANDLER": "api.exceptions.custom_exception_handler",
}

JWT_AUTH = {
    "JWT_AUTH_HEADER_PREFIX": "Bearer",
    "JWT_EXPIRATION_DELTA": timedelta(days=31),
    "JWT_RESPONSE_PAYLOAD_HANDLER": "api.jwt.jwt_response_payload_handler",
}

# Application definition

INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "apps.smear.apps.SmearConfig",
    "apps.user.apps.UserConfig",
    "rest_framework",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_filters",
    "rest_framework_jwt",
]

MIDDLEWARE = [
    "log_request_id.middleware.RequestIDMiddleware",
    "api.logging.AddGameIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "api.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "api.wsgi.application"


# Database
# https://docs.djangoproject.com/en/2.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": "playsmear",
        "USER": "postgres",
        "PASSWORD": "",
        "HOST": "postgres",
        "PORT": "5432",
    }
}


# Password validation
# https://docs.djangoproject.com/en/2.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/

STATIC_ROOT = os.path.join(PROJECT_ROOT, "staticfiles")
MEDIA_URL = None
STATIC_URL = "/"
WHITENOISE_INDEX_FILE = True
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Extra places for collectstatic to find static files.
STATICFILES_DIRS = (
    os.path.join(PROJECT_ROOT, "static"),
    "/static/www",
)


def skip_status_requests(record):
    return not ("GET /api/smear/v1/games/" in record.msg and "/status/ HTTP" in record.msg)


GENERATE_REQUEST_ID_IF_NOT_IN_HEADER = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "{levelname} {asctime} {name} {lineno} {funcName} [game:{game_id}] [{request_id}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "filters": ["request_id", "game_id", "skip_status_requests"],
            "formatter": "default",
        },
    },
    "filters": {
        "skip_status_requests": {
            "()": "django.utils.log.CallbackFilter",
            "callback": skip_status_requests,
        },
        "request_id": {
            "()": "log_request_id.filters.RequestIDFilter",
        },
        "game_id": {
            "()": "django.utils.log.CallbackFilter",
            "callback": add_game_id_filter,
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
        "django.server": {
            "filters": ["skip_status_requests"],
            "propagate": False,
        },
        "faker": {
            "level": "ERROR",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
}

ANONYMOUS_EMAIL = "is_anonymous@playsmear.com"
TAWK_KEY = os.getenv("TAWK_KEY", "amazing, I have the same key on my luggage")
