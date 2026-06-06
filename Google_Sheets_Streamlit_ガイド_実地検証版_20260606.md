# ゼロから Google Sheets を Streamlit アプリのバックエンドDBにする方法

**📝 2026-06-06 実地検証版（v3）**
本書は、改訂版（v2）を土台に、実際に最後（GitHub への push まで）まで通した経験で得た知見を反映して磨き上げたものです。机上の説明だけでなく、**実際に詰まった箇所とその解決**を本文・トラブル表・付録に織り込みました。主な追加・修正点は末尾「改訂履歴」を参照。

---

## この版で「実際にやってみて」分かった重要ポイント（先読み）

最初にハマりやすい所だけ要約します。詳細は各フェーズに。

1. **ヘッダーは「別々のセル」に入れる。** `name` と `score` を1セルにまとめて（タブ込みで）入れてしまうと、`A1 = "name\tscore"` のような1列データになり、アプリの2列前提と噛み合いません。→ フェーズ3で検出・修正方法を解説。
2. **Streamlit を起動する前に、接続だけを単体テストする。** `gspread` を直接使う十数行のスクリプトで「API有効化・共有・シート名」を一気に検証できます。切り分けが劇的に速くなります。→ フェーズ4に追加。
3. **`conn.read()` の既定キャッシュは 3600 秒。** `st-gsheets-connection` のソース上の既定は `ttl=3600`。だから「書き込み直前 `ttl=0`／書き込み後 `cache_data.clear()`」が重要。→ フェーズ4-6。
4. **GitHub で複数アカウントを使っていると push で詰まる。** `Permission to <別アカウント> denied to <今の鍵のアカウント>` が出ます。原因は「SSHの既定鍵が別アカウント扱い」。→ フェーズ5に専用セクションを新設。
5. **秘密鍵は「ログ・チャット・Issue」に絶対貼らない。** 一度どこかに出たら漏洩扱い。出してしまったら即ローテーション。→ セキュリティ節。

---

## 全体像（5つのフェーズ）

1. **Google Cloud側** でサービスアカウントを作る（＝アプリ専用のロボットユーザー）
2. **Google Sheets API と Google Drive API を有効化** する
3. 対象のスプレッドシートをそのロボットに **共有** する
4. **Streamlitアプリ側** でライブラリを入れて接続コードを書く
5. **Streamlit Cloud にデプロイ** して Secrets に認証情報を貼る

---

## フェーズ1: Google Cloud プロジェクトとサービスアカウントの作成

### 1-1. Google Cloud Console にアクセス
https://console.cloud.google.com/ にアクセスして、Googleアカウントでログイン。

### 1-2. 新規プロジェクトを作る（既存でもOK）
画面上部のプロジェクト選択 →「新しいプロジェクト」→ 名前を付けて作成。
（例: `my-streamlit-sheets`。既存プロジェクトを流用してもOK。）

### 1-3. サービスアカウントを作成
左メニュー「IAMと管理」→「サービスアカウント」→「サービスアカウントを作成」

- **名前**: `streamlit-sheets-bot` など分かりやすい名前
- **サービスアカウントID**: 自動で埋まる（例: `streamlit-sheets-bot@<プロジェクトID>.iam.gserviceaccount.com`）← **このメアドが後で重要！**
- **説明**: 任意

「作成して続行」→ ロール付与はスキップでOK（Sheetsへのアクセスはシート側で個別に付与するため）→「完了」

### 1-4. キー（JSONファイル）をダウンロード
作成したサービスアカウントをクリック → 上部タブ「キー」→「鍵を追加」→「新しい鍵を作成」→「JSON」→「作成」
→ JSONファイルがダウンロードされる。これが認証情報。**安全に保管！ GitHubに絶対上げない！**

> 💡 **新しい鍵JSONには `universe_domain` という項目が増えている**ことがあります（例: `"universe_domain": "googleapis.com"`）。`secrets.toml` には書いても書かなくても動きます（標準の10項目があれば十分）。
>
> 💡 鍵ファイルは `<プロジェクトID>-<英数字>.json` のような名前で落ちてきます。**これ自体が秘密**なので、`secrets/` 等の専用フォルダに置くと管理しやすいです。

---

## フェーズ2: Google Sheets API と Google Drive API を有効化

左メニュー「APIとサービス」→「ライブラリ」→ 検索欄に **Google Sheets API** → クリック →「有効にする」。
続けて **Google Drive API** も同じ手順で **必ず有効化**。

> ⚠️ **サービスアカウント方式では Drive API は「任意」ではなく必須**です。`st-gsheets-connection` は内部で `gspread` を使ってスプレッドシートを開きますが、その際に Drive API を利用するためです。
> ここを飛ばすと、後で次のエラーで止まります：
> `APIError: Google Drive API has not been used in project ... before or it is disabled`

---

## フェーズ3: スプレッドシートをサービスアカウントに共有（＋ヘッダーの作り方）

**一番忘れがちで詰まりやすい**ステップです。

1. Google スプレッドシートを開く（新規でもOK）。
2. 右上の「共有」ボタンをクリック。
3. 「ユーザーやグループを追加」欄に、フェーズ1-3のサービスアカウントのメアド（`xxx@xxx.iam.gserviceaccount.com`）を貼り付け。
4. 権限を「**編集者**」に（読み込みだけなら「閲覧者」でも可。書き込みもするなら編集者）。
5. 「通知を送信」のチェックは外してOK（ロボット宛なので無意味）。
6. 「共有（送信）」をクリック。

共有を忘れると `gspread.exceptions.SpreadsheetNotFound` や **403** になります。

### ⭐ 実地の落とし穴：ヘッダーが「1セルにまとまる」事故

> 練習用に A列 `name` / B列 `score` のヘッダーを作るとき、**`name` と `score` の間にタブを含んだまま 1つのセルに貼り付けてしまう**ことがあります。すると `A1` の中身が `name␉score`（タブ込みの1セル）になり、`B1` は空のまま。
> この状態だと `conn.read()` は **「`name␉score` という名前の1列」** として読み込み、追記フォームが作る `name` / `score` の2列と噛み合いません。

**検出方法**: `B1` をクリックして中身が `score` になっているか確認。空なら事故です。
（コードなら `gspread` で `ws.acell("A1").value` を見ると `'name\tscore'` のように出ます。）

**修正方法**: `A1` に `name`、`B1` に `score` を別々に入れ直すだけ。サービスアカウントが編集者なら、次の数行でプログラム的にも直せます。

```python
import gspread
gc = gspread.service_account(filename="<あなたの鍵>.json")
ws = gc.open_by_key("<スプレッドシートのキー>").worksheet("Scores")
ws.update_acell("A1", "name")
ws.update_acell("B1", "score")
print(ws.get_all_values())  # => [['name', 'score']] になればOK
```

> シート名（タブ名）は本書では **`Scores`** に統一します。コードの `worksheet="Scores"` と一致させてください。

---

## フェーズ4: Streamlit アプリのコード

### 4-1. プロジェクトフォルダ

```
my-app/
├── streamlit_app.py
├── requirements.txt
├── .gitignore
└── .streamlit/
    ├── secrets.toml          ← ローカル開発用（★Gitにcommitしない！）
    └── secrets.toml.example  ← 雛形（プレースホルダのみ。これは共有OK）
```

### 4-2. requirements.txt

```
streamlit>=1.28
st-gsheets-connection
```

> 💡 `gspread` は `st-gsheets-connection` の依存に自動で含まれるので明示不要（書いても害なし）。`st.connection()` は Streamlit 1.28 以降で安定。

### 4-3. .streamlit/secrets.toml（ローカル開発用）

ダウンロードしたJSONの中身を **TOML形式に転記**します。

```toml
[connections.gsheets]
spreadsheet = "<対象スプレッドシートのURL>"
type = "service_account"
project_id = "<your-project-id>"
private_key_id = "<your-private-key-id>"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "streamlit-sheets-bot@<your-project>.iam.gserviceaccount.com"
client_id = "<your-client-id>"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "<your-cert-url>"
```

> ⚠️ **重要ポイント**
> - 一番上の `spreadsheet` に対象シートの **URL**（または名前）を指定すると、コード側が楽。
> - `private_key` の改行は **`\n` のまま**（JSONの `\n` を本物の改行に置換しない）。TOMLのダブルクォート文字列は `\n` を改行として解釈するので、これで正しく動く。本物の改行を入れるとTOML構文エラー。
> - このファイルは必ず `.gitignore` で除外。

#### 💡 手で転記せず「JSON→TOMLを自動生成」する（転記ミス防止）

`private_key` の `\n` を手で扱うと事故りがち。次のスクリプトで安全に生成できます（`json.dumps` がTOML互換のエスケープをしてくれる）。

```python
import json, os, stat
JSON_KEY = "<あなたの鍵>.json"
SPREADSHEET_URL = "<対象スプレッドシートのURL>"
fields = ["type","project_id","private_key_id","private_key","client_email",
          "client_id","auth_uri","token_uri",
          "auth_provider_x509_cert_url","client_x509_cert_url"]
with open(JSON_KEY, encoding="utf-8") as f:
    d = json.load(f)
lines = ["[connections.gsheets]", f"spreadsheet = {json.dumps(SPREADSHEET_URL)}"]
lines += [f"{k} = {json.dumps(d[k])}" for k in fields if k in d]
os.makedirs(".streamlit", exist_ok=True)
out = ".streamlit/secrets.toml"
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
os.chmod(out, stat.S_IRUSR | stat.S_IWUSR)  # 0o600 所有者のみ
print("生成:", out)
```

> 🔐 `secrets.toml` は **`chmod 600`（所有者のみ読み書き）**にしておくと安心。上のスクリプトは自動で設定します。

### 4-4. .gitignore

```gitignore
# 認証情報（絶対にコミットしない）
.streamlit/secrets.toml
*.json

# Python
__pycache__/
*.py[cod]
.venv/
venv/
```

> 💡 `*.json` は鍵を確実に除外する安全策ですが、プロジェクトで必要な JSON まで除外してしまうことがあります。その場合は鍵を `secrets/` のような専用フォルダに置き、`secrets/` だけを無視する方が安全です。

### 4-5. .streamlit/secrets.toml.example（共有用の雛形）

チームやリポジトリ向けに「形だけ」を示す雛形。**実鍵は入れない**ので commit してOK。`secrets.toml` をコピーして値をプレースホルダに置き換えたもの、と考えてください（4-3 のテンプレと同じ中身でOK）。

### ⭐ 4-6. 先に「接続だけ」を単体テストする（強く推奨）

Streamlit を起動する前に、**`gspread` で直接** 接続を確認すると、フェーズ1〜3（API有効化・共有・シート名）が一気に検証でき、切り分けが速くなります。

```python
import gspread
gc = gspread.service_account(filename="<あなたの鍵>.json")
sh = gc.open_by_key("<スプレッドシートのキー>")     # URLの /d/ と /edit の間がキー
print("タイトル:", sh.title)
print("ワークシート一覧:", [ws.title for ws in sh.worksheets()])
ws = sh.worksheet("Scores")
print("データ:", ws.get_all_values())
```

- ここで `SpreadsheetNotFound` / 403 → **共有忘れ**（フェーズ3）。
- `APIError: ... has not been used` → **API未有効化**（フェーズ2）。
- ワークシート一覧に `Scores` が無い → **シート名の不一致**。
- データが `[['name\tscore']]` のよう → **ヘッダー1セル事故**（フェーズ3の修正へ）。

> `st.connection` 経由でも同様に確認できます（実行コンテキスト外だと警告は出ますが読み取りは可能）。ただし最初は `gspread` 直接が一番シンプルです。

### 4-7. streamlit_app.py（読み取り＋追記、キャッシュ対策込み・実用版）

```python
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

WORKSHEET = "Scores"  # シートのタブ名と一致させる

st.set_page_config(page_title="Google Sheets 連携デモ", page_icon="📊")
st.title("📊 Google Sheets 連携デモ")

conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    return conn.read(worksheet=WORKSHEET)

st.subheader("現在のデータ")
if st.button("🔄 更新"):
    st.cache_data.clear()
    st.rerun()

try:
    df = load_data()
except Exception as e:
    st.error(
        "シートの読み込みに失敗しました。\n"
        "- サービスアカウントにシートを共有したか（403 / SpreadsheetNotFound）\n"
        "- Sheets API と Drive API を両方有効化したか\n"
        "- secrets.toml の private_key の改行が \\n のままか\n"
        f"詳細: {e}"
    )
    st.stop()

df_display = df.dropna(how="all")  # 末尾の全列NaN空行を除去
st.dataframe(df_display, use_container_width=True)
st.caption(f"行数: {len(df_display)}")

st.subheader("行を追加")
with st.form("add_row", clear_on_submit=True):
    name = st.text_input("名前 (name)")
    score = st.number_input("スコア (score)", min_value=0, step=1)
    submitted = st.form_submit_button("追加")

if submitted:
    if not name.strip():
        st.warning("名前を入力してください。")
        st.stop()
    # 書き込み直前は ttl=0 で最新を読み直す（ロスト・アップデート対策）
    latest_df = conn.read(worksheet=WORKSHEET, ttl=0).dropna(how="all")
    new_row = pd.DataFrame([{"name": name.strip(), "score": int(score)}])
    updated_df = pd.concat([latest_df, new_row], ignore_index=True)
    conn.update(worksheet=WORKSHEET, data=updated_df)
    # conn.update() は読み取りキャッシュを自動で消さない → 明示クリア
    st.cache_data.clear()
    st.success(f"追加しました: {name.strip()} / {int(score)}")
    st.rerun()
```

実行：

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

→ ブラウザでシートの内容（`name` / `score`）が表示され、フォームから追記できればOK。

### ⚠️ なぜ `ttl=0` と `st.cache_data.clear()` ＋ `st.rerun()` が要るのか

**(1) 書き込み直前の `ttl=0`**:
`st-gsheets-connection` の `conn.read()` は **既定で `ttl=3600`（=1時間キャッシュ）**（ライブラリのソースで確認済み）。書き込み直前に古いキャッシュを読むと、その間に他者が追加した行ごと **全体を上書きして消す** 恐れがあります（ロスト・アップデート）。そこで**書き込み直前だけ `ttl=0`** で最新を取得します。

> 補足：Streamlit 汎用の `st.connection` の説明では「ttl 未指定なら期限なしでキャッシュ」とされますが、**このライブラリは明示的に `ttl=3600` を既定にしています**。どちらにせよ「放っておくと古い表が返る」点は同じで、対策の必要性は変わりません。

**(2) 書き込み後の `st.cache_data.clear()` ＋ `st.rerun()`**:
`conn.update()` は **読み取りキャッシュを自動では消しません**。そのため `st.rerun()` だけだと先頭の `conn.read()` が古い表を返し続け、追加行が（最大キャッシュ期間）表示されません。`clear()` でキャッシュを消してから `rerun()` すれば確実に最新化されます。
（`clear()` はアプリ全体のキャッシュを消すため、大規模アプリでは対象を絞る設計も検討。）

---

## フェーズ5: GitHub に push → Streamlit Cloud にデプロイ

### 5-1. push する前の安全確認（最重要）

**秘密が含まれていないことを、push 前に必ず確認**します。

```bash
git init
git add .

# (A) ステージされた一覧に secrets.toml / *.json が無いことを確認
git diff --cached --name-only

# (B) 無視されているもの（=上がらない）を確認
git status --ignored --short | grep '^!!'

# (C) 念のため中身を全文スキャン（実鍵の痕跡が無いか）
git grep --cached -n "PRIVATE KEY" || echo "OK: 実鍵は見つかりません"
```

`.gitignore` が効いていれば、`secrets.toml` と `*.json` は (A) に出ず (B) に出ます。

```bash
git commit -m "feat: initial Streamlit × Google Sheets app"
git branch -M main          # 既定ブランチ名を main に統一（master/main 不一致による push 失敗を防止）
git remote add origin <リポジトリURL>
git push -u origin main
```

> push 後は、リモートにも秘密が無いか念のため確認できます（`gh` 利用時）：
> ```bash
> gh api repos/<owner>/<repo>/git/trees/main?recursive=1 --jq '.tree[].path'
> ```

### ⭐ 5-1b. 実地の落とし穴：GitHub で複数アカウントを使っている場合

複数の GitHub アカウント（個人用・別用途など）を1台のPCで使い分けていると、push でこのエラーが出ます：

```
ERROR: Permission to OWNER/REPO.git denied to OTHER_ACCOUNT.
```

**原因**: そのPCの **SSHの既定鍵が「別アカウント」に紐づいている**ため。`~/.ssh/config` で `Host github.com` の `IdentityFile` が別アカウントの鍵を指していると、`git@github.com:...` への接続は常にそのアカウントとして認証され、目的のリポジトリへの書き込みが拒否されます。

**今どのアカウントで認証されるか**を確認：

```bash
ssh -T git@github.com
# => Hi <アカウント名>! ... と出る。これが「今の既定」。
```

**解決策A（推奨・恒久的）: SSH の Host 別名を使う**
`~/.ssh/config` にアカウント専用の別名を作り、リポジトリの remote をその別名に向けます。

```sshconfig
# ~/.ssh/config
Host github.com-myacct
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_myacct   # そのアカウント用の鍵
    IdentitiesOnly yes
```

```bash
# その別名で「どのアカウントになるか」を確認
ssh -T git@github.com-myacct      # => Hi <目的のアカウント>! になればOK

# remote を別名に切り替え
git remote set-url origin git@github.com-myacct:OWNER/REPO.git
git push -u origin main
```

> 鍵が GitHub 側のアカウントに登録されていれば、`ssh -T` の応答でそのアカウント名が返ります。**「鍵ファイル名」ではなく「GitHub上どのアカウントに登録された鍵か」で判定される**点に注意（名前が紛らわしくても、応答が真実）。

**解決策B: `gh` CLI ＋ HTTPS を使う**
GitHub CLI を目的のアカウントでログインし、git の認証を `gh` に任せます。

```bash
gh auth login
#   What account?            -> GitHub.com
#   Preferred protocol?      -> HTTPS   ← SSHを選ぶと既定鍵問題が残るので注意
#   Authenticate Git?        -> Yes
#   How to authenticate?     -> Login with a web browser
#   （ブラウザは「目的のアカウント」でログイン済みにしてから承認）

gh auth setup-git           # gh を git の認証ヘルパーに設定（HTTPS用）
git remote set-url origin https://github.com/OWNER/REPO.git
git push -u origin main     # gh のトークン（目的のアカウント）で認証される
```

> ⚠️ **ブラウザで今ログインしているアカウントに注意**。別アカウントのままブラウザ承認すると、また権限不足になります。
> ⚠️ `gh auth login` で **SSH を選ぶと、結局このPCの既定SSH鍵の問題が残る**ことがあります（別名を併用しないと別アカウント扱いになる）。複数アカウント環境では **HTTPS＋setup-git** か **解決策Aの別名** が確実です。

### 5-2. Streamlit Cloud でアプリ作成

1. https://share.streamlit.io/ →「Create app」
2. リポジトリ・ブランチ（`main`）・ファイル（`streamlit_app.py`）を選択
3. 「Advanced settings」→「Secrets」欄に、ローカルの `secrets.toml` の中身を **そっくりそのままコピペ**
4. **Deploy!**

デプロイ後にURLが発行され、公開アプリになります。

---

## ハマりポイントと対処（実地反映版）

| 症状 | 原因 | 解決 |
|---|---|---|
| `PermissionError` / 403 / `SpreadsheetNotFound` | シートにサービスアカウントを共有していない | フェーズ3をやり直す（メアドは `client_email`） |
| `APIError: API has not been used` | Sheets API または Drive API が無効 | フェーズ2で **両方** 有効化されているか確認 |
| `private_key` で改行/TOMLエラー | TOMLの改行表記ミス | `\n` のままにする・ダブルクォートで囲む（4-3の自動生成が安全） |
| **読み込んだら1列しかない / 列名が `name␉score`** | **ヘッダーを1セルにまとめて入れた** | **A1=`name`, B1=`score` と別セルに入れ直す**（フェーズ3） |
| 書き込みが反映されない | キャッシュ（`conn.update()` は消さない） | 書き込み前 `conn.read(ttl=0)`、書き込み後 `st.cache_data.clear()` → `st.rerun()` |
| 書き込んだら他の行が消えた | 古いキャッシュのまま全体を上書き | 書き込み直前に `ttl=0` で最新を読み直す |
| ローカルでは動くがCloudでエラー | Secretsの貼り忘れ | Cloud側の Secrets を再確認 |
| `quota exceeded` / 429 | API のリクエスト上限超過 | アクセス頻度を下げる／キャッシュ活用（「規模の限界」参照） |
| **`git push` で `Permission to A denied to B`** | **PCの既定SSH鍵が別アカウント** | **SSH別名（解決策A）** か **gh＋HTTPS（解決策B）**。`ssh -T git@github.com` で現在のアカウントを確認 |
| **`gh auth login` でSSHを選んだら別アカウントになる** | 既定SSH鍵が別アカウント | **HTTPSを選ぶ**か、SSH別名を併用 |
| `src refspec main does not match any` | 既定ブランチが `master` 等 | `git branch -M main` してから push |

---

## セキュリティの再確認（強化）

- **JSONキーと `secrets.toml` は絶対 GitHub に上げない**（`.gitignore` 徹底＋push前スキャン）。
- **`private_key` を「チャット・ログ・Issue・スクショ」に貼らない。** 一度どこかに出たら漏洩扱いです。`secrets.toml` は `chmod 600` に。
- **万一、鍵が漏れた／どこかに貼ってしまったら、即ローテーション**：
  1. Cloud Console → 該当サービスアカウント →「キー」で **古い鍵を削除**
  2. **新しい JSON を発行**してダウンロード
  3. ローカルの `secrets.toml` と、（デプロイ後は）**Cloud の Secrets も差し替え**
- サービスアカウントには **必要最小限のシートだけ共有**（プロジェクト全体に強い権限を付けない）。
- 公開アプリで個人情報を扱うなら、シートではなく別のDBを検討。

---

## 「バックエンドDB」として使うときの規模の限界

Google Sheets は手軽ですが、本来のデータベースではありません。

- **API レート制限**: Google Sheets API は概ね「1分あたり 60 リクエスト/ユーザー、プロジェクト単位で約 300/分」程度（数値は変わり得るので最新の公式ドキュメントで確認）。同時アクセスや高頻度の読み書きで 429 / quota exceeded。
- **同時書き込みに弱い**: 「全行を読む→書き戻す」方式は、複数人同時で取りこぼし（ロスト・アップデート）が起きます。`ttl=0` で緩和できるが完全には防げません。
- **データ量・速度の限界**: 行数が増えるほど読み書きが遅くなります。

👉 小規模・個人用・社内ツール・プロトタイプには最適。多人数同時・大量データ・厳密な整合性が必要なら **PostgreSQL / Firestore など本来のDB**を検討。

---

## おすすめの進め方（切り分けしやすい順）

1. 新しいスプレッドシートを作り、**A1=`name`, B1=`score`** を**別セル**で入れる。
2. フェーズ1〜3（サービスアカウント／API有効化／共有）を済ませる。
3. **フェーズ4-6 の `gspread` 単体テスト**で接続だけ先に通す。
4. `streamlit run` で読み取り表示 → 追記フォームを試す。
5. push前スキャン → GitHub へ push（複数アカウントなら 5-1b）→ Cloud にデプロイ。

この順なら、途中で詰まっても原因を切り分けやすいです。

---

## 改訂履歴

### 2026-06-06 実地検証版（v3）— 本版
実際に GitHub への push まで通した経験を反映：

- **【新設】ヘッダー1セル事故**（`A1="name\tscore"`）の検出・修正をフェーズ3に追加。実際に発生し、`gspread` で `A1`/`B1` を入れ直して解決。
- **【新設】接続の単体テスト**（`gspread` 直接）をフェーズ4-6に追加。Streamlit起動前に API/共有/シート名を一括検証できる。
- **【修正】キャッシュ既定値**: v2 の「既定は期限なし」という補足を訂正。`st-gsheets-connection` の `read()` は**ソース上 `ttl=3600` が既定**（実ソースで確認）。v1の「3600秒」が正しい。対策（`ttl=0`／`clear()`）の重要性は不変。
- **【新設】GitHub 複数アカウントの罠**（`Permission to A denied to B`）をフェーズ5に新設。`ssh -T` での現アカウント確認、SSH別名（解決策A）、`gh`＋HTTPS（解決策B）、`gh auth login` のプロトコル選択の注意を明記。
- **【追加】push前の秘密スキャン**（`git diff --cached`／`git status --ignored`／`git grep --cached "PRIVATE KEY"`）と、push後のリモート確認（`gh api ... trees`）。
- **【追加】secrets.toml の自動生成スクリプト**（`json.dumps` で `\n` を安全にエスケープ）と **`chmod 600`**。
- **【追加】`secrets.toml.example`** 雛形パターン（実鍵なしで共有可）。
- **【強化】セキュリティ**: 「秘密鍵をチャット/ログに貼らない」「貼ったら即ローテーション」を明記。
- **【改良】streamlit_app.py**: 末尾空行の除去（`dropna`）、読み込みエラーの分かりやすい表示、更新ボタン、入力検証、`clear_on_submit` を追加。

### 2026-06-06 改訂版（v2）からの引き継ぎ
- フェーズ2: Drive API を「必須」に修正（理由＝gspread が使用、エラー例明記）。
- フェーズ4-6: 書き込み例にロスト・アップデート対策とキャッシュクリアを追加。
- 規模の限界・代替DBの明記。
- フェーズ5-1: `git branch -M main` を追加。
- requirements.txt の整理（重複 gspread 削除、`streamlit>=1.28` 明記）。
- secrets.toml / .gitignore の安全注意。
