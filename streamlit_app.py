"""
Google Sheets を Streamlit アプリのバックエンドDBとして使うデモ。

- 読み取り: conn.read() でシート全体を DataFrame として取得
- 書き込み: フォームから1行追加し、conn.update() で書き戻す
- キャッシュ対策:
    * 書き込み直前は conn.read(ttl=0) で最新を読み直す（ロスト・アップデート対策）
    * 書き込み後は st.cache_data.clear() + st.rerun() で表示を最新化
      （conn.update() は読み取りキャッシュを自動では消さないため）
"""

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

WORKSHEET = "Scores"  # 対象ワークシート名（シート側のタブ名と一致させる）

st.set_page_config(page_title="Google Sheets 連携デモ", page_icon="📊")
st.title("📊 Google Sheets 連携デモ")

# 接続を確立（認証情報は .streamlit/secrets.toml の [connections.gsheets] を参照）
conn = st.connection("gsheets", type=GSheetsConnection)


@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    """表示用に既存データを読む。300秒キャッシュ（手動更新ボタンで即更新可）。"""
    return conn.read(worksheet=WORKSHEET)


# --- 現在のデータを表示 ---
st.subheader("現在のデータ")

col_a, col_b = st.columns([1, 4])
with col_a:
    if st.button("🔄 更新"):
        st.cache_data.clear()
        st.rerun()

try:
    df = load_data()
except Exception as e:  # noqa: BLE001  接続・共有・API 有効化のいずれかが原因
    st.error(
        "シートの読み込みに失敗しました。\n\n"
        "確認ポイント:\n"
        "- サービスアカウントにシートを「編集者」で共有したか（403 / SpreadsheetNotFound）\n"
        "- Google Sheets API と Drive API を両方有効化したか（APIError: ... has not been used）\n"
        "- secrets.toml の private_key の改行が \\n のままか（TOML 構文エラー）\n\n"
        f"詳細: {e}"
    )
    st.stop()

# read() は末尾に全列 NaN の空行を含むことがあるので、空行は落として表示
df_display = df.dropna(how="all")
st.dataframe(df_display, use_container_width=True)
st.caption(f"行数: {len(df_display)}")

# --- 追記フォーム ---
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

    # conn.update() は読み取りキャッシュを自動で消さないため、明示的にクリア
    st.cache_data.clear()
    st.success(f"追加しました: {name.strip()} / {int(score)}")
    st.rerun()
