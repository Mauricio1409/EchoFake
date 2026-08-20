from datetime import timedelta
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
env.read_env(str(BASE_DIR / '.env'))


SECRET_KEY = env('SECRET_KEY')
DEBUG = env.bool('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'apps.api'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.api.middleware.JWTPageAuthMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

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

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.api.authentication.CookieJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=env.int('JWT_ACCESS_MINUTES', default=30)),
    'REFRESH_TOKEN_LIFETIME': timedelta(hours=env.int('JWT_REFRESH_HOURS', default=12)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
}

# Cookies que llevan el JWT: httpOnly (no legibles por JS) para que tanto las
# páginas Django (vía JWTPageAuthMiddleware) como la API (vía CookieJWTAuthentication)
# se autentiquen con el mismo par access/refresh, sin tocar cada fetch() del sitio.
JWT_ACCESS_COOKIE = 'echofake_access'
JWT_REFRESH_COOKIE = 'echofake_refresh'
JWT_COOKIE_SECURE = not DEBUG
JWT_COOKIE_SAMESITE = 'Strict'

WSGI_APPLICATION = 'core.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

CELERY_BROKER_URL = env('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND')
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"

# External APIs (deepfake features)
ELEVENLABS_API_KEY = env('ELEVENLABS_API_KEY', default='')
ELEVENLABS_BASE_URL = env('ELEVENLABS_BASE_URL', default='https://api.elevenlabs.io')
FAL_KEY = env('FAL_KEY', default='')
FAL_BASE_URL = env('FAL_BASE_URL', default='https://queue.fal.run')
FAL_STORAGE_URL = env('FAL_STORAGE_URL', default='https://rest.fal.ai')
FAL_MODEL = env('FAL_MODEL', default='veed/fabric-1.0')
FAL_RESOLUTION = env('FAL_RESOLUTION', default='480p')
FAL_POLL_INTERVAL = env.float('FAL_POLL_INTERVAL', default=3.0)
FAL_POLL_TIMEOUT = env.float('FAL_POLL_TIMEOUT', default=300.0)
FAL_OBJECT_TTL_SECONDS = env.int('FAL_OBJECT_TTL_SECONDS', default=3600)
FAL_PLATFORM_URL = env('FAL_PLATFORM_URL', default='https://api.fal.ai/v1')
FAL_ADMIN_KEY = env('FAL_ADMIN_KEY', default='')
