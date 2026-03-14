import streamlit as st
from rdagent.log.ui.page_style import apply_shared_page_style, render_app_sidebar

st.set_page_config(page_title="用户管理 · AlphaFlow", page_icon="👥", layout="wide")
apply_shared_page_style()

if not st.session_state.get("auth_token"):
    st.switch_page("login.py")

render_app_sidebar("pages/users.py")

user = st.session_state.get("user", {})
role = user.get("role", "viewer")

if role != "admin":
    st.warning("仅管理员可访问用户管理。")
    st.stop()

st.title("👥 用户管理")

mock_users = [
    {"name": "Alice", "email": "alice@example.com", "role": "admin", "status": "active"},
    {"name": "Bob", "email": "bob@example.com", "role": "user", "status": "active"},
    {"name": "Carol", "email": "carol@example.com", "role": "viewer", "status": "disabled"},
]

st.dataframe(mock_users, use_container_width=True)

with st.expander("邀请用户"):
    name = st.text_input("姓名")
    email = st.text_input("邮箱")
    role_new = st.selectbox("角色", ["admin", "user", "viewer"], index=1)
    if st.button("发送邀请"):
        st.success(f"已邀请 {email}，角色 {role_new}")
