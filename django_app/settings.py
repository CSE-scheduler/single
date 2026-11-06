"""
日程調整アプリ（schedule）の設定。

秘密の値（SECRET_KEY・設定画面のパスワード・MySQLの接続情報）は
django_app/local_settings.py に書く（GitHubには上げない。local_settings_example.py をコピーして作る）。
local_settings.py がない手元の環境では、開発用の値（DEBUG=True、SQLite）で動く。
"""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


# ---- 開発用の値。本番（PythonAnywhere）では local_settings.py で上書きする ----
DEBUG = True
SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production"
ALLOWED_HOSTS = []
# 設定画面（/setting/home）に入るためのパスワード
SCHEDULE_ADMIN_PASSWORD = "1234"
# MySQLを使うときは local_settings.py に MYSQL = {"NAME": ..., "USER": ..., "PASSWORD": ..., "HOST": ...} を書く
MYSQL = None

try:
    from .local_settings import *  # noqa: F401,F403
except ImportError:
    pass

if not DEBUG:
    if SECRET_KEY.startswith("django-insecure"):
        raise ImproperlyConfigured("local_settings.py に SECRET_KEY を設定してください。")
    if SCHEDULE_ADMIN_PASSWORD == "1234":
        raise ImproperlyConfigured("local_settings.py に SCHEDULE_ADMIN_PASSWORD を設定してください。")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "schedule",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "django_app.urls"

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

WSGI_APPLICATION = "django_app.wsgi.application"


if MYSQL:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": MYSQL["NAME"],
            "USER": MYSQL["USER"],
            "PASSWORD": MYSQL["PASSWORD"],
            "HOST": MYSQL["HOST"],
            "PORT": MYSQL.get("PORT", ""),
            "OPTIONS": {
                "charset": "utf8mb4",  # 日本語を正しく保存する
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            # 同時に予約が入っても「database is locked」にならないよう、空くまで待つ
            "OPTIONS": {"timeout": 20},
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
# 時刻は日本時間のままデータベースに保存する
USE_TZ = False

STATIC_URL = "static/"
# collectstatic で集める場所。PythonAnywhereの「Static files」で /static/ をここに割り当てる
STATIC_ROOT = BASE_DIR / "staticfiles"

# 説明書のアップロード（上限は schedule/forms.py の MANUAL_MAX_BYTES）
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
