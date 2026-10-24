import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "development-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
INSTALLED_APPS = ["django.contrib.contenttypes", "django.contrib.auth", "django.contrib.staticfiles", "rest_framework", "drf_spectacular", "products"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "products.middleware.CorsMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth"]}}]
STATIC_URL = "static/"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.getenv("DRF_DB_PATH", str(BASE_DIR / "products.sqlite3"))}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {"DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema", "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"], "EXCEPTION_HANDLER": "products.exceptions.api_exception_handler"}
SPECTACULAR_SETTINGS = {"TITLE": "Product API · Django REST Framework", "DESCRIPTION": "Product CRUD comparison API", "VERSION": "1.0.0", "SERVE_INCLUDE_SCHEMA": False}
