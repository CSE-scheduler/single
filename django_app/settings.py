"""
日程調整アプリ（schedule）の設定。

サーバーごとの値（SECRET_KEY・設定画面のパスワード・メール・データベース・ロゴなど）は
django_app/local_settings.py に書く。GitHubには上げない（local_settings_example.py をコピーして作る）。
local_settings.py がない手元の環境では、開発用の値（DEBUG=True、SQLite、メールはターミナルに表示）で動く。

このファイルの順番：
  1. 開発用の初期値      … local_settings.py で上書きできる
  2. local_settings.py を読む
  3. 1・2 から決まる値   … ここは上書きしない
"""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


# ======== 1. 初期値（local_settings.py で上書きできる） ========

DEBUG = True
SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# 設定画面（/setting/home）のパスワードを、ハッシュにしたもの。
# 次のコマンドで作り、local_settings.py に書く（書いていないあいだは設定画面にログインできない）：
#   python manage.py make_admin_password
SCHEDULE_ADMIN_PASSWORD_HASH = ""

# ---- メール（予約確認メール・キャンセルのメール） ----
# SMTPサーバー。Gmailなら下のまま、大学や研究室のメールサーバーなら書き換える
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True   # ポート587（STARTTLS）のとき True
EMAIL_USE_SSL = False  # ポート465（SSL）のとき True（EMAIL_USE_TLS は False にする）
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
EMAIL_TIMEOUT = 10
# 差出人。空なら EMAIL_HOST_USER を使う。名前をつけるなら '"○○研究室 実験予約" <address@example.com>'
DEFAULT_FROM_EMAIL = ""
# メールを実際に送るか。None なら「EMAIL_HOST_PASSWORD を書いたら送る」
# （パスワードのいらない学内のメールサーバーを使うときは True にする）
SEND_EMAIL = None

# ---- データベース ----
# 何も書かなければ SQLite（db.sqlite3）。MySQLなら MYSQL = {...} を書くだけでよい。
# PostgreSQL など、ほかのデータベースは local_settings.py に DATABASES = {...} を直接書く
MYSQL = None

# ---- 見た目（研究室ごとに変えるところ） ----
# 左上のロゴと favicon。site_static/ フォルダ（GitHubには上げない）に画像を置けば、そのファイル名を書くだけで差し替えられる
SITE_NAME = "CSE Scheduler"
SITE_LOGO = "schedule/image/cse-logo.png"
SITE_FAVICON = "schedule/image/cse-favicon.png"

# ---- その他 ----
LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"  # 枠の時刻はこのタイムゾーンで扱う
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # collectstatic で集める場所。Webサーバーから /static/ として配信する

try:
    from .local_settings import *  # noqa: F401,F403
except ImportError:
    pass


# ======== 3. 1・2 から決まる値 ========

if not DEBUG and SECRET_KEY.startswith("django-insecure"):
    raise ImproperlyConfigured("local_settings.py に SECRET_KEY を設定してください。")

if SEND_EMAIL is None:
    SEND_EMAIL = bool(EMAIL_HOST_PASSWORD)
if SEND_EMAIL:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    # 送らずに、送るはずだったメールをターミナル（ログ）に出す
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = DEFAULT_FROM_EMAIL or EMAIL_HOST_USER or "webmaster@localhost"

if "DATABASES" not in globals():
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

# 研究室ごとの画像を置くフォルダ（あれば使う）
STATICFILES_DIRS = [BASE_DIR / "site_static"] if (BASE_DIR / "site_static").is_dir() else []


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
                "schedule.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "django_app.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

USE_I18N = True
# 時刻は TIME_ZONE の時刻のままデータベースに保存する
USE_TZ = False

# 説明書のアップロード（上限は schedule/forms.py の MANUAL_MAX_BYTES）
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
