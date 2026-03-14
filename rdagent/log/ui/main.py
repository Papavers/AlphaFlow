from pathlib import Path

import streamlit as st

from rdagent.log.ui.page_style import apply_shared_page_style, render_app_sidebar, render_page_hero, render_section_intro
from rdagent.log.ui.utils_logscan import scan_logs


def _go(page: str) -> None:
    st.switch_page(page)


st.set_page_config(page_title="AlphaFlow 首页", page_icon="🚀", layout="wide")
apply_shared_page_style()

if not st.session_state.get("auth_token"):
    st.switch_page("pages/login.py")

render_app_sidebar("main.py")

user = st.session_state.get("user", {})
log_root = Path(st.session_state.get("log_root", "./log"))
tasks, factors = scan_logs(log_root)

render_page_hero(
    "AlphaFlow 首页",
    None,
)

main_col, side_col = st.columns([1.7, 1], gap="large")

with main_col:
    with st.container(border=True):
        render_section_intro("核心入口")
        core_col1, core_col2 = st.columns(2)
        with core_col1:
            if st.button("进入任务工作台", use_container_width=True, type="primary"):
                _go("pages/home.py")
            if st.button("查看任务历史", use_container_width=True):
                _go("pages/tasks.py")
        with core_col2:
            if st.button("查看因子记录", use_container_width=True):
                _go("pages/factors.py")
            if st.button("结果回放", use_container_width=True):
                _go("pages/playback.py")

    with st.container(border=True):
        render_section_intro("最近任务")
        if tasks:
            recent = tasks[:5]
            st.table(
                {
                    "ID": [task.id for task in recent],
                    "状态": [task.status for task in recent],
                    "时间": [task.created_at for task in recent],
                }
            )
        else:
            st.empty()

with side_col:
    with st.container(border=True):
        render_section_intro("其他入口")
        aux_col1, aux_col2 = st.columns(2)
        with aux_col1:
            if st.button("用户管理", use_container_width=True):
                _go("pages/users.py")
        with aux_col2:
            if st.button("设置", use_container_width=True):
                _go("pages/settings.py")

    with st.container(border=True):
        render_section_intro("原版工作台")
        st.page_link("pages/legacy.py", label="打开原版工作台", icon="↗")
