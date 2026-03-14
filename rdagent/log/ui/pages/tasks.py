import streamlit as st
from pathlib import Path
import pandas as pd
from rdagent.log.ui.utils_logscan import scan_logs, read_log_tail
from rdagent.log.ui.page_style import apply_shared_page_style, render_app_sidebar, render_page_hero, render_section_intro
from rdagent.log.ui.task_launcher import TASK_SPECS


def _status_label(status: str | None) -> str:
    return {
        "success": "已完成",
        "failed": "失败",
        "running": "运行中",
        "ended": "已结束",
    }.get(status or "", status or "-")


def _prompt_preview(prompt: str | None, limit: int = 42) -> str:
    content = (prompt or "").strip()
    if not content:
        return "-"
    return content if len(content) <= limit else content[: limit - 1] + "…"


def _task_title(record) -> str:
    task_id = (record.request_meta or {}).get("task_id", "")
    return TASK_SPECS.get(task_id, {}).get("title", record.id)


def _build_table(records) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "任务": [_task_title(t) for t in records],
            "状态": [_status_label(t.status) for t in records],
            "时间": [t.created_at for t in records],
            "类型": [t.task_type or "-" for t in records],
            "提示词": [_prompt_preview(t.prompt) for t in records],
            "目录": [t.log_dir.name for t in records],
        }
    )

st.set_page_config(page_title="任务历史 · AlphaFlow", page_icon="📑", layout="wide")
apply_shared_page_style()

if not st.session_state.get("auth_token"):
    st.switch_page("login.py")

render_app_sidebar("pages/tasks.py")

render_page_hero("任务历史", "这里看全部任务记录、提示词和运行结果，适合复盘与对比。", None)

log_root = Path(st.session_state.get("log_root", "./log"))
tasks, _ = scan_logs(log_root)

status_filter = st.multiselect("状态", ["success", "failed", "running", "ended"], default=["success", "failed", "running", "ended"], label_visibility="visible")
keyword = st.text_input("搜索 (ID/名称/类型)", placeholder="输入关键词过滤")

filtered = [t for t in tasks if t.status in status_filter]
if keyword:
    kw = keyword.lower()
    filtered = [
        t
        for t in filtered
        if kw in t.id.lower()
        or kw in t.name.lower()
        or (t.task_type and kw in t.task_type)
        or kw in ((t.prompt or "").lower())
    ]

top_col1, top_col2, top_col3, top_col4 = st.columns(4)
top_col1.metric("任务总数", len(tasks))
top_col2.metric("运行中", sum(1 for t in tasks if t.status == "running"))
top_col3.metric("已完成", sum(1 for t in tasks if t.status == "success"))
top_col4.metric("带提示词", sum(1 for t in tasks if (t.prompt or "").strip()))

if filtered:
    render_section_intro("任务列表", "支持按状态、关键词和提示词检索。")
    st.dataframe(_build_table(filtered), use_container_width=True, hide_index=True)
else:
    st.info("暂无匹配的任务。")

st.markdown("---")
st.subheader("任务详情")
ids = [t.id for t in filtered]
if ids:
    selected = st.selectbox("选择任务", ids, index=0)
else:
    selected = None

if selected:
    record = next(t for t in filtered if t.id == selected)
    c1, c2, c3 = st.columns(3)
    c1.metric("状态", _status_label(record.status))
    c2.metric("创建时间", record.created_at)
    c3.metric("类型", record.task_type or "-")
    c4, c5, c6 = st.columns(3)
    c4.metric("产物数", len(record.artifacts or []))
    c5.metric("日志目录", record.log_dir.name)
    c6.metric("Owner", record.owner or "-")

    request_meta = record.request_meta or {}
    render_section_intro("本次请求", "保留从页面发起任务时的关键参数，便于复用。")
    meta_col1, meta_col2, meta_col3 = st.columns(3)
    meta_col1.metric("任务名称", _task_title(record))
    meta_col2.metric("循环次数", request_meta.get("loop_n") or "-")
    meta_col3.metric("最长时长", request_meta.get("all_duration") or "-")
    if (record.prompt or "").strip():
        with st.expander("查看提示词", expanded=True):
            st.write(record.prompt)
    elif request_meta:
        st.caption("该任务未填写提示词。")

    st.markdown("**日志尾部 (stdout.log)**")
    tail_txt = read_log_tail(record.log_dir, n=120)
    if tail_txt:
        st.code(tail_txt, language="text")
    else:
        st.info("未找到日志或暂无内容。")

    st.markdown("**产物**")
    if record.artifacts:
        st.write(record.artifacts)
    else:
        st.caption("暂无产物")

    if request_meta.get("report_files"):
        st.markdown("**上传报告**")
        st.write(request_meta.get("report_files"))

    st.markdown("**操作**")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🧭 去工作台回放", use_container_width=True):
            st.session_state["pending_log_path"] = record.log_dir.relative_to(log_root) if log_root.exists() else record.log_dir
            st.switch_page("legacy.py")
    with col_b:
        if st.button("📜 打开回放页", use_container_width=True):
            st.session_state["pending_log_path"] = record.log_dir.relative_to(log_root) if log_root.exists() else record.log_dir
            st.switch_page("playback.py")
else:
    st.caption("请选择一个任务查看详情。")

st.divider()
if st.button("🔄 刷新", use_container_width=True):
    st.rerun()
