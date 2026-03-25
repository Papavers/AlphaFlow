import streamlit as st
from rdagent.log.ui.page_style import apply_shared_page_style, render_page_hero, render_section_intro
from rdagent.log.ui import auth_file

st.set_page_config(page_title="注册 · AlphaFlow", page_icon="📝", layout="centered")
apply_shared_page_style()

render_page_hero("注册新用户", None)

auth_file.init_store()

with st.container(border=True):
    render_section_intro("创建账号")
    with st.form("register_form"):
        name = st.text_input("姓名（可选）")
        email = st.text_input("邮箱", placeholder="you@example.com")
        password = st.text_input("密码", type="password")
        password2 = st.text_input("确认密码", type="password")
        submitted = st.form_submit_button("注册", use_container_width=True)

if submitted:
    if not email or not password:
        st.error("邮箱和密码为必填项")
    elif password != password2:
        st.error("两次输入的密码不一致")
    else:
        try:
            auth_file.create_user(email, password, name=name)
            st.success("注册成功，请登录。")
            st.page_link("pages/login.py", label="去登录")
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"注册失败：{e}")
