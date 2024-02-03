import os
import re
import sys
from datetime import timedelta
from pathlib import Path

import sentry_sdk
from decouple import Csv, config
from sentry_sdk.integrations.django import DjangoIntegration

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
OTP_TOTP_THROTTLE_FACTOR = 1

DEBUG = config('DEBUG', cast=bool, default=False)
STAGING = config('STAGING', cast=bool, default=False)
TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'

BLOCKLINK_TOKEN = config('BLOCKLINK_TOKEN')
BLOCKLINK_BASE_URL = config('BLOCKLINK_BASE_URL', default='https://blocklink.raastin.com')

DEBUG_OR_TESTING = DEBUG or TESTING
DEBUG_OR_TESTING_OR_STAGING = DEBUG or TESTING or STAGING


HOST_URL = config('HOST_URL', default='https://api.raastin.com')
PANEL_URL = config('PANEL_URL', default='https://raastin.com')

CELERY_TASK_ALWAYS_EAGER = config('CELERY_ALWAYS_EAGER', default=False)

KAFKA_HOST_URL = config('KAFKA_HOST_URL', default='')

# Application definition

INSTALLED_APPS = [
    'admin_interface',
    'colorfield',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_admin_listfilter_dropdown',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'hijack',
    'hijack.contrib.admin',
    'django_filters',
    'drf_yasg',
    'simple_history',
    'django_user_agents',
    'django_otp',
    'django_otp.plugins.otp_totp',

    'analytics',
    'financial',
    'multimedia',
    'accounts',
    'accounting',
    'ledger',
    'market',
    'jalali_date',
    'stake',
    'gamify',
    'health',
    'marketing',

    'tinymce',
    'import_export',
    'django_quill',
]


MIDDLEWARE = [
    'allow_cidr.middleware.AllowCIDRMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'hijack.middleware.HijackUserMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
    'django_user_agents.middleware.UserAgentMiddleware',

    'accounts.middleware.SetLocaleMiddleware',
    'django_otp.middleware.OTPMiddleware'
]

# todo: fix csrf check
MIDDLEWARE.insert(0, 'accounts.middleware.DisableCsrfCheck')
MIDDLEWARE.remove('django.middleware.csrf.CsrfViewMiddleware')

if DEBUG:
    MIDDLEWARE.remove('hijack.middleware.HijackUserMiddleware')

ROOT_URLCONF = '_base.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates']
        ,
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

WSGI_APPLICATION = '_base.wsgi.application'

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv(), default='')
ALLOWED_CIDR_NETS = ['10.0.0.0/16']

CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', cast=Csv(), default='')
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', cast=Csv(), default='')
CORS_ALLOW_CREDENTIALS = True

DATABASES = {
    'default': {
        'ENGINE': config('DEFAULT_DB_ENGINE', default='django.db.backends.postgresql_psycopg2'),
        'NAME': config('DEFAULT_DB_NAME', default='core_db'),
        'USER': config('DEFAULT_DB_USER', default='exchange'),
        'PASSWORD': config('DEFAULT_DB_PASSWORD'),
        'HOST': config('DEFAULT_DB_HOST', default='localhost'),
        'PORT': config('DEFAULT_DB_PORT', default=5432),
    }
}

LOCAL_REDIS_URL = config('LOCAL_REDIS_URL', default='redis://127.0.0.1:6379')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': LOCAL_REDIS_URL + '/0',

        'OPTIONS': {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
    'token': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': LOCAL_REDIS_URL + '/1',

        'OPTIONS': {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
}

MARKET_CACHE_LOCATION = LOCAL_REDIS_URL + '/3'
METRICS_CACHE_LOCATION = LOCAL_REDIS_URL + '/4'

PRICE_CACHE_LOCATION = config('PRICE_CACHE_LOCATION', default='redis://127.0.0.1:6379/2')
MASTER_PRICE_CACHE_LOCATION = config('MASTER_PRICE_CACHE_LOCATION', default=None)
SOCKET_SERVER_CACHE_LOCATION = config('SOCKET_SERVER_CACHE_LOCATION', default='redis://127.0.0.1:6379')

# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    # {
    #     'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    # },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    # {
    #     'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    # },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/

LANGUAGE_CODE = config('LOCALE', default='fa-IR')
LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale/'),
]

TIME_ZONE = config('TIME_ZONE', default='Asia/Tehran')

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/

STATIC_URL = config('STATIC_URL', default='/static/')
STATIC_ROOT = config('STATIC_ROOT', default=os.path.join(BASE_DIR, 'public/'))

STATICFILES_DIRS = [
    'static'
]

MEDIA_URL = config('MEDIA_URL', default='/media/')
MEDIA_ROOT = config('MEDIA_ROOT', default=os.path.join(BASE_DIR, 'media/'))

if not DEBUG_OR_TESTING:
    INSTALLED_APPS.append('django_minio_backend')

    DEFAULT_FILE_STORAGE = "django_minio_backend.models.MinioBackend"
    STATICFILES_STORAGE = "django_minio_backend.models.MinioBackendStatic"

    MINIO_ENDPOINT = config('MINIO_STORAGE_ENDPOINT')
    MINIO_ACCESS_KEY = config('MINIO_STORAGE_ACCESS_KEY')
    MINIO_SECRET_KEY = config('MINIO_STORAGE_SECRET_KEY')
    MINIO_EXTERNAL_ENDPOINT_USE_HTTPS = True
    MINIO_USE_HTTPS = False

    MINIO_PRIVATE_BUCKETS = [
        'core-media',
    ]
    MINIO_PUBLIC_BUCKETS = [
        'core-static',
    ]

MINIO_EXTERNAL_ENDPOINT = config('MINIO_CDN_ENDPOINT')
MINIO_MEDIA_FILES_BUCKET = 'core-media'
MINIO_STATIC_FILES_BUCKET = 'core-static'

MINIO_STORAGE_STATIC_URL = f'https://{MINIO_EXTERNAL_ENDPOINT}/{MINIO_STATIC_FILES_BUCKET}'
MINIO_STORAGE_MEDIA_URL = f'https://{MINIO_EXTERNAL_ENDPOINT}/{MINIO_MEDIA_FILES_BUCKET}'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

ENV = 'staging' if STAGING else 'production'

sentry_sdk.init(
    dsn=config("SENTRY_DSN", default=''),
    integrations=[
        DjangoIntegration(),
    ],
    environment=ENV,

    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production.
    traces_sample_rate=0,

    # If you wish to associate users to errors (assuming you are using
    # django.contrib.auth) you may enable sending PII data.
    send_default_pii=True
)

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ] if DEBUG else [
        'rest_framework.renderers.JSONRenderer',
    ],
    # 'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'DEFAULT_PAGINATION_CLASS': None,
    'PAGE_SIZE': 20,

    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        # 'rest_framework.authentication.TokenAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],

    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.coreapi.AutoSchema',

    'DEFAULT_THROTTLE_RATES': {
        'burst': '50/min',
        'sustained': '500/day',
        # 'burst_api': '40/min',
        # 'sustained_api': '20000/day',
        'burst_api': '200/min',
        'sustained_api': '200000/day',
    },
    'EXCEPTION_HANDLER': 'accounts.throttle.custom_exception_handler'
}

if config('JWT_PRIVATE_KEY', None):
    SIMPLE_JWT = {
        'ROTATE_REFRESH_TOKENS': False,
        'BLACKLIST_AFTER_ROTATION': False,
        'AUTH_HEADER_TYPES': ('Bearer', 'JWT'),
        'ALGORITHM': 'RS256',
        'SIGNING_KEY': config('JWT_PRIVATE_KEY', default=''),
        'VERIFYING_KEY': config('JWT_PUBLIC_KEY', default=''),
        'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    }

AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = ('accounts.backends.AuthenticationBackend',)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'formatters': {
        'verbose': {
            'format': '[contactor] %(levelname)s %(asctime)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
        'sentry': {
            'level': 'WARNING',
            'filters': ['require_debug_false'],
            'class': 'sentry_sdk.integrations.logging.EventHandler',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console', 'sentry'],
            'level': 'DEBUG',
            'propagate': False,
        },
    }
}


SESSION_COOKIE_SAMESITE = config('SESSION_COOKIE_SAMESITE', default='None')
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', cast=bool, default=True)

if config('SESSION_COOKIE_DOMAIN', default=None):
    SESSION_COOKIE_DOMAIN = config('SESSION_COOKIE_DOMAIN')

if config('CSRF_COOKIE_DOMAIN', default=None):
    CSRF_COOKIE_DOMAIN = config('CSRF_COOKIE_DOMAIN')

CSRF_COOKIE_SAMESITE = config('CSRF_COOKIE_SAMESITE', default='None')
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', cast=bool, default=True)

JALALI_DATE_DEFAULTS = {
    'Strftime': {
        'date': '%y/%m/%d',
        'datetime': '%H:%M:%S _ %y/%m/%d',
    },
    'Static': {
        'js': [
            'admin/js/django_jalali.min.js',
        ],
        'css': {
            'all': [
                'admin/jquery.ui.datepicker.jalali/themes/base/jquery-ui.min.css',
            ]
        }
    },
}

SYSTEM_ACCOUNT_ID = config('SYSTEM_ACCOUNT_ID', default=1)
OTC_ACCOUNT_ID = config('OTC_ACCOUNT', cast=int)
RANDOM_TRADER_ACCOUNT_ID = config('BOT_RANDOM_TRADER_ACCOUNT_ID', default=None)
MARKET_MAKER_ACCOUNT_ID = config('MARKET_MAKER_ACCOUNT_ID', cast=int, default=0)
TRADER_ACCOUNT_ID = config('TRADER_ACCOUNT_ID', cast=int, default=0)
MARGIN_INSURANCE_ACCOUNT = config('MARGIN_INSURANCE_ACCOUNT', cast=int, default=None)
MARGIN_POOL_ACCOUNT = config('MARGIN_POOL_ACCOUNT', cast=int, default=0)

BRAND_EN = config('BRAND_EN', default='')
BRAND = config('BRAND', default='')

OTP_TOTP_ISSUER = BRAND_EN
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

TRADE_ENABLE = config('TRADE_ENABLE', cast=bool, default=True)
MARKET_TRADE_ENABLE = config('MARKET_TRADE_ENABLE', cast=bool, default=True)
WITHDRAW_ENABLE = config('WITHDRAW_ENABLE', cast=bool, default=True)

TINYMCE_JS_URL = os.path.join(MINIO_STORAGE_STATIC_URL, "tinymce/tinymce.min.js")

EXCLUSIVE_SMS_NUMBER = config('EXCLUSIVE_SMS_NUMBER', default=None)

LOGIN_URL = PANEL_URL + '/auth/login'
