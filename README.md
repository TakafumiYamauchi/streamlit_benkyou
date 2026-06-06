# 📊 Streamlit × Google Sheets 連携デモ

Google スプレッドシートを Streamlit アプリのバックエンドDBとして使うサンプル。
サービスアカウント経由でシートを読み書きします（小規模・個人用・プロトタイプ向け）。

## 構成

```
.
├── streamlit_app.py            # アプリ本体（読み取り＋追記フォーム）
├── requirements.txt            # 依存ライブラリ
├── .gitignore                  # 秘密情報を確実に除外
└── .streamlit/
    └── secrets.toml.example    # 認証情報の雛形（★実鍵は入れない）
```

> ⚠️ `*.json`（サービスアカウント鍵）と `.streamlit/secrets.toml`（実際の認証情報）は
> `.gitignore` で除外しており、リポジトリには含まれません。**絶対にコミットしないでください。**

## ローカルでの実行

1. 依存をインストール
   ```bash
   pip install -r requirements.txt
   ```
2. `.streamlit/secrets.toml.example` を `.streamlit/secrets.toml` にコピーし、
   ダウンロードしたサービスアカウント JSON の中身を転記する。
   - `private_key` の改行は `\n` のまま（本物の改行に置換しない）。
   - `spreadsheet` に対象シートの URL を入れる。
3. 起動
   ```bash
   streamlit run streamlit_app.py
   ```

## Streamlit Cloud へのデプロイ

1. このリポジトリを GitHub に push（秘密情報が含まれないことを `git status` で確認）。
2. https://share.streamlit.io/ → **Create app** → リポジトリ・ブランチ・`streamlit_app.py` を選択。
3. **Advanced settings → Secrets** に、ローカルの `secrets.toml` の中身をそのまま貼り付ける。
4. **Deploy**。

## 事前準備（Google Cloud 側）

1. サービスアカウントを作成し、JSON 鍵をダウンロード。
2. **Google Sheets API** と **Google Drive API** を両方有効化（Drive は必須）。
3. 対象スプレッドシートを、サービスアカウントの `client_email` に「編集者」で共有。

## 規模の限界（重要）

Google Sheets は本来のDBではありません。API レート制限（おおむね 1分あたり 60 リクエスト/ユーザー程度）、
同時書き込みでのロスト・アップデート、データ量増加による速度低下があります。
多人数同時・大量データ・厳密な整合性が必要なら PostgreSQL / Firestore などを検討してください。
