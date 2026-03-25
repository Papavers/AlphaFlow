import streamlit as st
from rdagent.log.ui.page_style import apply_shared_page_style, render_app_sidebar
from rdagent.log.ui import auth_file

st.set_page_config(page_title="用户管理 · AlphaFlow", page_icon="👥", layout="wide")
apply_shared_page_style()

if not st.session_state.get("auth_token"):
    st.info("请先登录")
    st.stop()

render_app_sidebar("pages/users.py")

user = st.session_state.get("user", {})
role = user.get("role", "viewer")

if role != "admin":
    st.warning("仅管理员可访问用户管理。")
    st.stop()

st.title("👥 用户管理")

auth_file.init_store()
users = auth_file.list_users()
if users:
    import pandas as pd

    df = pd.DataFrame(users)
    st.dataframe(df.sort_values(["role", "email"]), use_container_width=True)
else:
    st.info("当前无用户（已由系统在首次运行时创建初始管理员）。")

st.markdown("---")
with st.form("manage_user"):
    emails = [u["email"] for u in users]
    if not emails:
        st.write("没有可管理的用户")
    else:
        sel = st.selectbox("选择用户", emails)
        target = next((u for u in users if u["email"] == sel), None)
        st.write(target)
        new_role = st.selectbox("设置角色", ["admin", "user", "viewer"], index=["admin","user","viewer"].index(target.get("role","user")))
        active = st.checkbox("激活用户", value=target.get("active", True))
        delete = st.checkbox("删除该用户（不可撤销）", value=False)
        if st.form_submit_button("应用变更"):
            try:
                if delete:
                    auth_file.delete_user(sel)
                    st.success(f"已删除 {sel}")
                else:
                    auth_file.set_user_role(sel, new_role)
                    auth_file.set_user_active(sel, active)
                    st.success("已保存变更")
                st.experimental_rerun()
            except Exception as e:
                st.error(str(e))

st.markdown("---")
with st.expander("注册新用户"):
    st.markdown("请使用注册页面：")
    st.page_link("pages/register.py", label="注册新用户")
