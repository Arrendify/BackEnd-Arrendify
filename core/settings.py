# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

import os
from decouple import config
from unipath import Path
import boto3
from botocore.client import Config

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = Path(__file__).parent
CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='S#perS3crEt_1122')

# SECURITY WARNING: don't run with debug turned on in production!
#DEBUG = config('DEBUG', default=False, cast=bool)
DEBUG = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': 'Logs/django.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
        'apps.api': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}

# load production server
ALLOWED_HOSTS = [config('SERVER', default='127.0.0.1'), config('SERVER2', default='127.0.0.1'), "192.168.1.24","192.168.3.2","ec2-3-129-70-24.us-east-2.compute.amazonaws.com","192.168.1.86","192.168.1.141","127.0.0.1","api-prod-w-industries.sekurilynx.com"]

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'apps.home.apps.HomeAppConfig',  # Enable the inner home (home)
    'apps.api',  # Enable the inner home (home)
    'apps.accounts',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    # 'rest_framework.authentication.TokenAuthentication'
    'rest_auth',
    'storages',

]

TOKEN_EXPIRED_AFTER_SECONDS = 21600

# Autenticación
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',
        #'rest_framework_jwt.authentication.JSONWebTokenAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        # 'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),    
}

# Specify the authentication backend to be used for token authentication
# Here we use the JSONWebTokenBackend provided by djangorestframework-jwt
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',  # Django's built-in authentication backend
    # 'rest_framework.authentication.TokenAuthentication',  # Token authentication provided by DRF
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',

]

CORS_ORIGIN_WHITELIST = (
    # 'https://arrendify.app',
    'https://contrato.pro',
    "https://crm.zoho.com",
    "https://creator.zoho.com",
    #saul
    'http://192.168.2.73:8000',
    'http://192.168.1.140:8000',
    'http://192.168.1.86:8000',
    'http://192.168.1.141:8000',
    #yo
    'http://192.168.1.24:8000',
    'http://192.168.0.233:8000',
    'http://192.168.3.2:8001',
    'http://192.168.3.2:8000',
    'http://192.168.1.190:8000',
    'http://localhost',
)
# CORS_ORIGIN_ALLOW_ALL = True
# CORS_ALLOW_METHODS = (
#     'GET',
#     'POST',
#     'PUT',
#     'PATCH',
#     'DELETE',
#     'OPTIONS'
# )

#STRIPE
STRIPE_SECRET_KEY = config("stripe_secreta", "tu_clave_secreta")
STRIPE_PUBLIC_KEY = config("stripe_publica", "tu_clave_publica")
STRIPE_WEBHOOK_SECRET = config("webhook_stripe", "tu_clave_webhook")


ROOT_URLCONF = 'core.urls'
LOGIN_REDIRECT_URL = "home"  # Route defined in home/urls.py
LOGOUT_REDIRECT_URL = "home"  # Route defined in home/urls.py
TEMPLATE_DIR = os.path.join(CORE_DIR, "apps/templates")  # ROOT dir for templates


#configuracion Aws
AWS_ACCESS_KEY_ID = config('lola', default='AWSSecret')
AWS_SECRET_ACCESS_KEY = config('lols', default='AWSSecret')
AWS_STORAGE_BUCKET_NAME = config('asbn', default='AWSSecret')
AWS_S3_CUSTOM_DOMAIN = '%s.s3.amazonaws.com' % AWS_STORAGE_BUCKET_NAME
AWS_S3_REGION_NAME = 'us-east-2'
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}
AWS_LOCATION = 'static'
AWS_LOCATION_MEDIA = 'media'

AWS_DEFAULT_ACL = 'public-read'
STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
STATIC_URL = 'https://%s/%s/' % (AWS_S3_CUSTOM_DOMAIN, AWS_LOCATION)
MEDIA_URL = 'https://%s/%s/' % (AWS_S3_CUSTOM_DOMAIN, AWS_LOCATION_MEDIA )

# STATICFILES_DIRS = [
#     os.path.join(CORE_DIR, 'apps/static'),
#     ]






#############################################################
# SRC: https://devcenter.heroku.com/articles/django-assets

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.9/howto/static-files/
# STATIC_ROOT = os.path.join(CORE_DIR, 'static')
#STATIC_URL = '/static/'

# Extra places for collectstatic to find static files.
# STATICFILES_DIRS = (
#     os.path.join(CORE_DIR, 'apps/static'),
# )


#############################################################
#############################################################


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [TEMPLATE_DIR],
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

WSGI_APPLICATION = 'core.wsgi.application'

# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql_psycopg2',
#         'NAME': "postgres",
#         'USER': 'arrendify',
#         'PASSWORD': 'Arrendy.123',
#         'HOST': 'arrendifyapp.cnw0xwrwd9ir.us-east-2.rds.amazonaws.com',
#         'PORT': '5432',
#     }
# }


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': "postgres",
        'USER': 'contratopro',
        'PASSWORD': 'Arrendy.123',
        'HOST': 'contratopro.cnw0xwrwd9ir.us-east-2.rds.amazonaws.com',
        'PORT': '5432',
    }
}


# DATABASES = {
#    'default': {
#        'ENGINE': 'django.db.backends.sqlite3',
#        'NAME': 'db.sqlite3',
#   }
# }

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = 'es-mx'

TIME_ZONE = 'America/Cancun'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# ALLOWED_HOSTS = ['*']


AUTH_USER_MODEL = 'accounts.CustomUser'

# SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
# SESSION_CACHE_ALIAS = 'default'
# SESSION_COOKIE_SECURE = True

#ZAPSIGN
API_TOKEN_ZAPSIGN = config("API_TOKEN_ZAPSIGN", "tu_clave_secreta")
API_URL_ZAPSIGN = config("API_URL_ZAPSIGN", "https://api.zapsign.com.br")