import streamlit as st
from rdagent.log.ui.page_style import apply_shared_page_style, render_page_hero, render_section_intro
from rdagent.log.ui import auth_file
import uuid


st.set_page_config(page_title="登录 · AlphaFlow", page_icon="🔐", layout="centered")
apply_shared_page_style()

render_page_hero("登录 AlphaFlow", None)

auth_file.init_store()
auth_file.ensure_admin_exists()

with st.container(border=True):
    render_section_intro("账号登录")
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("邮箱", placeholder="you@example.com")
        password = st.text_input("密码", type="password", placeholder="请输入密码")
        submitted = st.form_submit_button("进入工作台", type="primary", use_container_width=True)

    st.markdown("---")
    st.page_link("pages/register.py", label="没有账号？ 注册新用户")

if submitted:
    if not email or not password:
        st.error("请输入邮箱和密码")
    else:
        user = auth_file.authenticate_user(email, password)
        if user:
            token = uuid.uuid4().hex
            st.session_state["auth_token"] = token
            st.session_state["user"] = user
            # set per-user log root for isolation
            from pathlib import Path

            role = user.get("role", "user")
            if role == "admin":
                log_root = Path("./log")
            else:
                # isolate normal users under log/users/{email}
                safe_email = user.get("email", "anonymous").replace("@", "_at_").replace(".", "_")
                log_root = Path("./log/users") / safe_email
            log_root.mkdir(parents=True, exist_ok=True)
            st.session_state["log_root"] = str(log_root)

            st.success("登录成功，正在跳转…")
            try:
                st.switch_page("pages/home.py")
            except Exception:
                # fallback to rerun if switch_page not supported in this env
                try:
                    st.experimental_rerun()
                except Exception:
                    pass
        else:
            st.error("认证失败：邮箱或密码错误，或用户已被禁用。")
