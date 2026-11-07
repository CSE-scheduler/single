# CSE Scheduler（日程調整）

実験の参加日時を予約してもらうための Django アプリです。実験ごとに「プロジェクト」を作り、募集ページ・設定・予約をプロジェクトごとに分けて管理します。

- 公開先：https://csescheduler.pythonanywhere.com/
- 設定画面：https://csescheduler.pythonanywhere.com/setting/home （パスワードが必要）

---

## 画面

| URL | 画面 |
| --- | --- |
| `/<プロジェクト名>/` | 参加者用。同意画面 → 日時の選択 → 入力 → 予約完了 |
| `/<プロジェクト名>/reservation/<予約ごとの文字列>` | 参加者用。予約の確認・日時の変更・キャンセル（確認メールのリンクから開く） |
| `/setting/home` | プロジェクト一覧。作成・削除 |
| `/setting/home/<プロジェクト名>` | プロジェクトの編集 |
| `/setting/home/<プロジェクト名>/appointments` | 予約一覧（参加者一覧） |

---

## 使い方

### プロジェクト一覧

- 「新規プロジェクト作成」でプロジェクトを作ります。プロジェクト名は募集ページの URL になり、あとから変えられません。使えるのはアルファベット・数字・記号（`-_.~!$&'()*+,;=:@`）だけです。
- 一覧には、ステータス（● 公開中／● 停止中）、参加者数（押すと予約一覧）、募集ページの URL とコピーボタンが出ます。

### プロジェクトの編集

編集画面の入力欄は、入力したその場で自動保存されます（右下に「保存しました」と出ます）。

**タイトルの行**
- プロジェクト名・ステータス・募集ページの URL（コピーボタンつき）。
- 右端の「停止する」で募集を止めます。モーダルで、募集ページに出す文言（例：本実験の募集は終了いたしました。）を入力します。停止中は「公開する」で再開できます。
- 停止中は、タイトルの下の「募集画面本文」でその文言を直せます。

**人数**：参加者数・今日以降の予約・支払い済み。「参加者一覧」で予約一覧へ移ります。

**募集予約カレンダーの設定**
- 募集期間：日付の範囲と時間帯（例：9:00〜21:00）。期間の外の枠は予約できません。作ったときは、今日から2週間（9:00〜21:00）です。
- 所要時間：0〜4時間・00〜50分（10分刻み）。予約は30分の枠を、所要時間に足りるだけ使います（例：40分 → 2枠）。
- 自動で閉鎖する枠：「今からn時間以内」「今日中」「次の日まで」「今日からn日後まで」のどれかに始まる枠は、予約を締め切ります。
- バッファ：オンにすると、予約の前・後ろ・前後の指定した時間（30分〜2時間）の枠を自動で閉じます。

**カレンダー**
- 枠は 8:00〜23:00 の30分ごとで、今日から90日後まで自動で作られます。表示するのは募集期間の時間帯の行だけです。
- マスを押すと、受付（◯）と受付停止（×）が切り替わります。
- マウスでドラッグして囲んだ範囲は、マスごとに反転します（◯ → ×、× → ◯）。
- 日付・時刻を押すと、その列・行をまとめて切り替えます（1つでも ◯ があれば全部 ×、全部 × なら全部 ◯）。
- 記号：◯ 受付中／× 受付停止／予 予約済み／未 実施済み（謝金未払い）／済 謝金支払い済み／N No Show／テ テスト用／- 募集対象外。予約の入ったマスを押すと、その日の予約一覧を開きます。

**最初の画面（同意画面）**
- ページタイトル（見出しになります）と本文。本文は1行ずつ段落になり、空の行は余白になります。
- 行の途中に `<a href="https://...">リンク</a>` や `<strong>強調</strong>` などの HTML タグを書けます。`https://` のない href には自動で `https://` がつき、そのまま書いた URL もリンクになります。
- 「説明書を添付する」をオンにするとモーダルでアップロードします（PDF・PNG・JPEG、10MBまで）。添付すると、参加者は「説明書を読む」を押すまで「次へ進む」を押せません。チェックを外すと説明書を削除します。

**取得するデータ**
- 氏名・年齢・性別・メールアドレス・データ再利用の許可と、その他1〜6（自由記述3つ・はい／いいえ3つ）から、入力画面に出す項目を選びます。すべて入力必須です。
- その他1〜6は、項目名が空のままチェックを入れると、モーダルで項目名を入力します。

**予約完了画面**
- ページタイトルと本文（同意画面と同じ書き方）。`{日時}` は予約した日時に置き換わります。
- 「遷移ボタンを設置する」をオンにすると、別のページ（事前アンケートなど）へ進むボタンを出します。文言か遷移先が空のときは、モーダルで入力します。

**予約確認メール**
- 「予約確認メールを送る」をオンにすると、予約したとき・日時を変更したときは確認メールを、キャンセルしたときはキャンセルのメールを、予約した人に送ります。返信用メールアドレスが空のときは、モーダルで入力します。オフのあいだはメールの欄を入力できません。
- 返信用メールアドレス：参加者がメールの「返信」を押すと、このアドレス宛てになります（メールの Reply-To）。
- 予約メールを自分も受け取る：返信用メールアドレスにも、同じメールが BCC で届きます（予約の通知の代わり）。
- タイトルと本文の `{日時}` `{氏名}` `{返信用メールアドレス}` `{キャンセル用URL}` は、予約ごとに置き換わります（入力欄では青字で表示されます）。`{キャンセル用URL}` は、その予約の確認・変更・キャンセルのページです。
- 日時を変更したときの確認メールは、タイトルの前に【日時の変更が完了しました】がつきます。

### 予約一覧

- 日付の範囲とステータス（複数選べます）で絞り込めます。変えるとその場で表が切り替わります。
- 列の見出しを押すと並べ替えます（もう一度押すと逆順）。
- ステータス（予約済み・実施済み（謝金未払い）・謝金支払い済み・No Show・テスト用）は、選んだその場で保存されます。
- 「削除」で予約を消すと、その枠は再び予約できるようになります（参加者にメールは送りません）。

### 参加者の流れ

1. 同意画面：本文を読み、説明書があれば「説明書を読む」を押してから「次へ進む」。
2. 日時の選択：予約できる開始時刻だけが ◯ です。空いていても、そこから所要時間ぶんの空きがない枠は薄い ◯（押せない）になります。
3. 入力：取得する項目を入力して申し込みます。
4. 予約完了：確認メールの設定があればメールが届きます。

確認メールのリンクから、始まる前の予約なら日時の変更・キャンセルができます。停止中のプロジェクトでは、新しい予約と日時の変更はできません（キャンセルはできます）。

---

## 手元で動かす

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

`django_app/local_settings.py` がないときは、開発用の設定（SQLite、メールは送らずにターミナルに表示）で動きます。http://127.0.0.1:8000/setting/home を開いてください。

テスト：

```bash
.venv/bin/python manage.py test schedule
```

---

## PythonAnywhere へのデプロイ（初回）

アカウント `csescheduler` の「Consoles」から **Bash** を開いて：

```bash
git clone https://github.com/CSE-scheduler/single.git
cd single
mkvirtualenv --python=python3.12 scheduler   # 仮想環境を作る（作ると自動で有効になる）
pip install -r requirements.txt

# 本番の設定ファイルを作り、SECRET_KEY（とメールを送るならGmailの設定）を書く
cp django_app/local_settings_example.py django_app/local_settings.py
python -c "import secrets; print(secrets.token_urlsafe(50))"   # これを SECRET_KEY に貼る
nano django_app/local_settings.py

python manage.py migrate
python manage.py collectstatic --noinput
```

次に「Web」タブで：

1. **Add a new web app** → ドメインは `csescheduler.pythonanywhere.com` → **Manual configuration** → **Python 3.12**
2. **Virtualenv** に `/home/csescheduler/.virtualenvs/scheduler` を入力
3. **Source code** と **Working directory** に `/home/csescheduler/single` を入力
4. **WSGI configuration file**（`/var/www/csescheduler_pythonanywhere_com_wsgi.py`）を開き、中身を全部消して次の内容にする

   ```python
   import os
   import sys

   path = '/home/csescheduler/single'
   if path not in sys.path:
       sys.path.insert(0, path)

   os.environ['DJANGO_SETTINGS_MODULE'] = 'django_app.settings'

   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```

5. **Static files** に URL `/static/`、Directory `/home/csescheduler/single/staticfiles` を追加
6. **Force HTTPS** をオンにする
7. 上の緑の **Reload** ボタンを押す

https://csescheduler.pythonanywhere.com/setting/home を開き、設定画面のパスワードでログインできれば完了です。

## 更新するとき

手元で変更を GitHub に push したあと、PythonAnywhere の Bash で：

```bash
cd ~/single
workon scheduler
git pull
python manage.py migrate
python manage.py collectstatic --noinput
```

最後に「Web」タブで **Reload** を押します。`migrate` と `collectstatic` は、変更がなければ何もしないので、毎回実行して大丈夫です。

CSS の URL にはファイルの更新時刻がつくので（`?v=...`）、更新後にブラウザに古い見た目が残ることはありません。

---

## 設定

### 本番の設定ファイル（`django_app/local_settings.py`）

`local_settings_example.py` をコピーして作ります。パスワードが入るので、GitHub には上げません（`.gitignore` に登録済み）。

| 項目 | 内容 |
| --- | --- |
| `DEBUG` | 本番は `False` |
| `SECRET_KEY` | ランダムな長い文字列（必須） |
| `ALLOWED_HOSTS` | `["csescheduler.pythonanywhere.com"]` |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | メールを送るときの Gmail アドレスとアプリパスワード |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | `True`（Force HTTPS とあわせて） |
| `MYSQL` | MySQL を使うときだけ（書かなければ `db.sqlite3`）。`requirements.txt` の `mysqlclient` の行も有効にする |

書き換えたら、「Web」タブで **Reload** を押します。

### 送信用の Gmail

メールは `local_settings.py` に書いた Gmail アカウントから送ります（PythonAnywhere の無料プランでも使えます）。書いていないあいだはメールを送らず、編集画面の「予約確認メール」に赤字で注意が出ます。

1. 送信に使う Google アカウントで2段階認証をオンにし、「アプリパスワード」（16文字）を作る
2. `local_settings.py` に書いて、Reload する

   ```python
   EMAIL_HOST_USER = "送信用のGmailアドレス"
   EMAIL_HOST_PASSWORD = "アプリパスワード"
   ```

メールが届かないときは、次を確認してください。

- 編集画面で「予約確認メールを送る」がオンになっているか（赤字のエラーがあると保存されません）
- 迷惑メールフォルダに入っていないか
- 「Web」タブの **Error log** に「予約のメールを送れませんでした」が出ていないか

### 設定画面のパスワード

`django_app/settings.py` の `SCHEDULE_ADMIN_PASSWORD_HASH` に、パスワードをハッシュにした値を書いています（GitHub に平文を置かないため）。変えるときは、次のコマンドで作った値に置き換えて push し、PythonAnywhere で更新します。

```bash
python manage.py shell -c "from django.contrib.auth.hashers import make_password; print(make_password('新しいパスワード'))"
```

---

## ファイル構成

```
django_app/
  settings.py                 設定（本番の値は local_settings.py で上書き）
  local_settings_example.py   本番の設定ファイルの見本
schedule/
  models.py         プロジェクト・枠・予約
  calendar.py       カレンダーの表と、枠が予約できるかの判定（所要時間・締め切り・バッファ）
  views.py          参加者の画面
  setting_views.py  設定画面
  forms.py          設定と予約の入力フォーム
  mail.py           予約確認メール・キャンセルのメール
  tests.py          テスト
  templates/schedule/          参加者の画面
  templates/schedule/setting/  設定画面
  static/schedule/css/         main.css（demogame と同じ見た目）と schedule.css
  static/schedule/image/       ロゴ・favicon
```

- 枠の時間帯（8:00〜23:00）や、自動で作る日数（90日）は `schedule/models.py` の `START_HOUR`・`N_SLOTS`・`DAYS_AHEAD` で変えられます。
- 時刻は日本時間（`TIME_ZONE = "Asia/Tokyo"`）で扱います。
