# 本番（PythonAnywhere）用の設定の見本。
# このファイルを同じフォルダに local_settings.py という名前でコピーして、値を書き換える。
# local_settings.py はパスワードが入るので、GitHubには上げない（.gitignoreに登録済み）。

DEBUG = False

# ランダムな長い文字列。次のコマンドで作れる：
#   python -c "import secrets; print(secrets.token_urlsafe(50))"
SECRET_KEY = "ここにランダムな文字列を書く"

ALLOWED_HOSTS = ["csescheduler.pythonanywhere.com"]

# 設定画面（/setting/home）に入るためのパスワード
SCHEDULE_ADMIN_PASSWORD = "ここに設定画面のパスワードを書く"

# HTTPSでだけクッキーを送る（PythonAnywhereの「Force HTTPS」をオンにしておく）
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# MySQLを使うときだけ書く（書かなければ db.sqlite3 を使う）。値はPythonAnywhereの「Databases」タブにある
# MYSQL = {
#     "NAME": "csescheduler$default",
#     "USER": "csescheduler",
#     "PASSWORD": "ここにMySQLのパスワードを書く",
#     "HOST": "csescheduler.mysql.pythonanywhere-services.com",
# }
