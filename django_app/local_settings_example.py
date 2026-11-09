# ===================================================================
#  本番サーバー用の設定ファイルの雛形
# ===================================================================
#
#  使い方：
#    1. このファイルを同じフォルダに local_settings.py という名前でコピーする
#         cp django_app/local_settings_example.py django_app/local_settings.py
#    2. 「★」のついた項目を、自分たちの値に書き換える
#    3. Webアプリを再起動する（PythonAnywhereなら「Web」タブの Reload）
#
#  local_settings.py にはパスワードが入るので、GitHubには上げない（.gitignore に登録済み）。
#  書かなかった項目は django_app/settings.py の初期値が使われる。
#  詳しい説明は docs/DEPLOY.md を見てください。


# -------------------------------------------------------------------
#  基本（必須）
# -------------------------------------------------------------------

DEBUG = False

# ★ ランダムな長い文字列。次のコマンドで作って貼る：
#     python -c "import secrets; print(secrets.token_urlsafe(50))"
SECRET_KEY = "ここにランダムな文字列を貼る"

# ★ このアプリを公開するドメイン（例：["yourlab.pythonanywhere.com"]、["schedule.example.ac.jp"]）
ALLOWED_HOSTS = ["your-domain.example.com"]

# ★ 設定画面（/setting/home）のパスワードをハッシュにしたもの。次のコマンドで作り、表示された1行に置き換える：
#     python manage.py make_admin_password
SCHEDULE_ADMIN_PASSWORD_HASH = ""

# HTTPS のときだけログイン用のクッキーを送る（HTTPS で公開するなら True のまま。HTTP のままだとログインできなくなる）
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# nginx などの後ろで動かし、HTTPS を nginx 側で受けるときは、次の行の # を外す
# （外さないと、メールに書く予約の確認ページのURLが http:// になったり、設定の保存が 403 になったりする）
# SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# -------------------------------------------------------------------
#  メール（予約確認メール・キャンセルのメール）
#  書かなければメールは送らない（編集画面に赤字で注意が出る）
# -------------------------------------------------------------------

# --- Gmail を使う場合（おすすめ：送信専用のアカウントを作る） ---
#   Googleアカウントで2段階認証をオンにし、「アプリパスワード」（16文字）を作って貼る。
#   アプリパスワードはアカウントのパスワードを変えると無効になるので、送信専用アカウントのパスワードは変えない。
# EMAIL_HOST_USER = "your-address@gmail.com"
# EMAIL_HOST_PASSWORD = "abcdabcdabcdabcd"

# --- 大学・研究室のメールサーバーを使う場合 ---
#   値はメールサーバーの管理者に確認する。
# EMAIL_HOST = "smtp.example.ac.jp"
# EMAIL_PORT = 587            # STARTTLS なら 587、SSL なら 465
# EMAIL_USE_TLS = True        # 587 のとき True
# EMAIL_USE_SSL = False       # 465 のとき True（EMAIL_USE_TLS は False に）
# EMAIL_HOST_USER = "your-address@example.ac.jp"
# EMAIL_HOST_PASSWORD = "パスワード"
# SEND_EMAIL = True           # パスワードのいらないサーバーで、EMAIL_HOST_PASSWORD を書かないときだけ

# 差出人の表示（空なら EMAIL_HOST_USER）。Gmail では EMAIL_HOST_USER と同じアドレスにする
# DEFAULT_FROM_EMAIL = '"○○研究室 実験予約" <your-address@gmail.com>'


# -------------------------------------------------------------------
#  データベース
#  書かなければ SQLite（プロジェクトのフォルダの db.sqlite3）。1研究室で使うなら SQLite で十分
#  ※ 再起動でファイルが消えるサーバー（一部のクラウドの無料プランなど）では、SQLite は使えない
# -------------------------------------------------------------------

# --- MySQL（PythonAnywhere の「Databases」タブで作れる）。requirements.txt の mysqlclient の行も有効にする ---
# MYSQL = {
#     "NAME": "yourname$default",
#     "USER": "yourname",
#     "PASSWORD": "MySQLのパスワード",
#     "HOST": "yourname.mysql.pythonanywhere-services.com",
# }

# --- PostgreSQL など（requirements.txt の psycopg の行も有効にする） ---
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": "schedule",
#         "USER": "schedule",
#         "PASSWORD": "パスワード",
#         "HOST": "localhost",
#         "PORT": "5432",
#     }
# }


# -------------------------------------------------------------------
#  見た目（任意）
# -------------------------------------------------------------------

# 左上のロゴと favicon を自分たちのものにする：
#   プロジェクトのフォルダに site_static/ を作って画像を置き、ファイル名を書く（site_static/ はGitHubに上げない）。
#   ロゴは横長の画像（高さ28pxで表示）、favicon は正方形の画像。変えたら collectstatic を実行する。
# SITE_NAME = "○○ Lab Scheduler"   # ロゴの代わりの文字（画像が読めないとき・読み上げ）
# SITE_LOGO = "logo.png"           # site_static/logo.png
# SITE_FAVICON = "favicon.png"     # site_static/favicon.png

# 枠の時刻のタイムゾーン（日本以外で使うときだけ）
# TIME_ZONE = "Asia/Tokyo"
