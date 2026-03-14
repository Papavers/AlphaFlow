import streamlit as st
from rdagent.log.ui.page_style import apply_shared_page_style, render_page_hero, render_section_intro

st.set_page_config(page_title="登录 · AlphaFlow", page_icon="🔐", layout="centered")
apply_shared_page_style()

render_page_hero(
    "登录 AlphaFlow",
    None,
)

with st.container(border=True):
    render_section_intro("账号登录")
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("邮箱", placeholder="you@example.com")
        password = st.text_input("密码", type="password", placeholder="请输入密码")
        role = st.selectbox("角色", ["user", "admin", "viewer"], index=0)
        submitted = st.form_submit_button("进入工作台", type="primary", use_container_width=True)

if submitted:
    if email and password:
        st.session_state["auth_token"] = "mock-token"
        st.session_state["user"] = {"email": email, "role": role}
        st.success("登录成功")
        st.switch_page("main.py")
    else:
        st.error("请输入邮箱和密码")
