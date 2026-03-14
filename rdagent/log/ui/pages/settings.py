import streamlit as st
from rdagent.log.ui.page_style import apply_shared_page_style, render_app_sidebar

st.set_page_config(page_title="设置 · AlphaFlow", page_icon="⚙️", layout="wide")
apply_shared_page_style()

if not st.session_state.get("auth_token"):
    st.switch_page("login.py")

render_app_sidebar("pages/settings.py")

st.title("⚙️ 设置（占位）")
st.info("此页预留给主题、通知、账号等设置。")
