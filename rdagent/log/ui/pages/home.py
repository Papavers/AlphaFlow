import streamlit as st
from pathlib import Path
import time
import re
import pandas as pd
import plotly.express as px
import fitz
from rdagent.log.ui.utils_logscan import scan_logs, list_log_dirs, TaskRecord
from rdagent.log.ui.results_parser import summarize_log_dir
from rdagent.log.ui.page_style import apply_shared_page_style, render_app_sidebar, render_page_hero, render_section_intro
from rdagent.log.ui.task_launcher import TASK_SPECS, launch_task, pid_alive, stop_task, tail_file


def _apply_prompt_example(prompt_key: str, example: str) -> None:
    st.session_state[prompt_key] = example


def _render_prompt_guide(spec: dict, prompt_key: str) -> None:
    guide = spec.get("prompt_guide") or {}
    if not guide:
        return
    with st.container(border=True):
        st.markdown("### ✍️ 提示词助手")
        st.caption("这里填的是业务目标和研究偏好，不是代码指令。页面启动时会把它作为额外要求注入；命令行直接运行仍保持原来的默认逻辑。")

        top_col1, top_col2 = st.columns([2, 1])
        with top_col1:
            st.markdown(f"**适合写什么：** {guide.get('good_for', '-')}")
            st.markdown(f"**推荐结构：** `{guide.get('template', '-')}`")
        with top_col2:
            st.info("建议先写方向，再写约束，最后写不要做什么。")

        tab1, tab2, tab3, tab4 = st.tabs(["该怎么做", "可以怎么做", "避免怎么做", "一键示例"])

        with tab1:
            for step in guide.get("how_to") or []:
                st.markdown(f"- {step}")

        with tab2:
            for item in guide.get("can_try") or []:
                st.markdown(f"- {item}")

        with tab3:
            for item in guide.get("avoid") or []:
                st.markdown(f"- {item}")

        with tab4:
            examples = guide.get("examples") or []
            if not examples:
                st.caption("当前任务暂无预置示例。")
            for idx, example in enumerate(examples, start=1):
                st.code(example, language="text")
                action_col1, action_col2 = st.columns([1, 4])
                with action_col1:
                    if st.button(f"填入示例{idx}", key=f"fill_{prompt_key}_{idx}", use_container_width=True):
                        _apply_prompt_example(prompt_key, example)
                        st.rerun()
                with action_col2:
                    st.caption("可直接填入后再按你的需求微调。")


def _render_prompt_quality_hint(prompt_text: str) -> None:
    content = (prompt_text or "").strip()
    if not content:
        st.info("可以留空直接运行；如果你有明确研究方向，建议补一句‘目标 + 约束’，效果会更稳定。")
        return
    if len(content) < 12:
        st.warning("这条提示词有点短，建议补充目标、约束或排除项，让系统更容易理解你的意图。")
        return
    if any(token in content.lower() for token in ["def ", "import ", "for ", "python", "pandas", "torch"]):
        st.warning("更建议写业务要求而不是代码实现，例如写‘优先低回撤、先做简单因子’，不要直接写代码。")
        return
    st.success("这条提示词结构已经比较清晰，可以直接启动；如果还想更稳，可以再补一个‘不要做什么’。")


def _fmt_pct(v):
    if v is None:
        return "-"
    try:
        return f"{float(v):.2%}"
    except Exception:
        return str(v)


def _get_active_task_state() -> dict:
    return st.session_state.setdefault(
        "home_active_task",
        {
            "pid": None,
            "task_id": None,
            "log_dir": None,
            "stdout_file": None,
            "meta_file": None,
            "command": None,
            "report_files": [],
            "prompt": "",
            "loop_n": None,
            "all_duration": None,
            "status": "idle",
            "created_at": None,
        },
    )


def _get_report_draft_store() -> dict:
    return st.session_state.setdefault("home_report_drafts", {})


def _normalize_uploaded_reports(uploaded_reports) -> list[dict]:
    normalized = []
    for uploaded_file in uploaded_reports or []:
        file_bytes = uploaded_file.getvalue()
        if not file_bytes:
            continue
        normalized.append(
            {
                "name": uploaded_file.name,
                "content": file_bytes,
                "size": len(file_bytes),
            }
        )
    return normalized


def _load_saved_report_items(report_files: list[str] | None) -> list[dict]:
    items: list[dict] = []
    for file_path in report_files or []:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except Exception:
            continue
        items.append({"name": path.name, "content": content, "size": len(content), "saved_path": str(path)})
    return items


def _sync_report_draft(task_id: str, uploaded_reports) -> list[dict]:
    draft_store = _get_report_draft_store()
    if uploaded_reports:
        draft_store[task_id] = _normalize_uploaded_reports(uploaded_reports)
    return draft_store.get(task_id, [])


def _clear_report_draft(task_id: str) -> None:
    draft_store = _get_report_draft_store()
    draft_store.pop(task_id, None)
    st.session_state.pop("home_report_uploader", None)


def _task_status_label(status: str | None) -> str:
    labels = {
        "running": "运行中",
        "success": "已完成",
        "failed": "失败",
        "ended": "已结束",
        "idle": "空闲",
    }
    return labels.get(status or "idle", status or "空闲")


def _prompt_preview(prompt: str | None, limit: int = 48) -> str:
    content = (prompt or "").strip()
    if not content:
        return "-"
    if len(content) <= limit:
        return content
    return content[: limit - 1] + "…"


def _find_task_record(tasks: list[TaskRecord], active_task: dict) -> TaskRecord | None:
    target_log_dir = active_task.get("log_dir")
    target_id = Path(target_log_dir).name if target_log_dir else None
    for task in tasks:
        if target_log_dir and str(task.log_dir) == str(target_log_dir):
            return task
        if target_id and task.id == target_id:
            return task
    return None


def _sync_active_task(active_task: dict, tasks: list[TaskRecord]) -> TaskRecord | None:
    if not active_task.get("task_id"):
        active_task["status"] = "idle"
        return None

    matched = _find_task_record(tasks, active_task)
    running = pid_alive(active_task.get("pid"))
    if matched is not None:
        active_task["created_at"] = matched.created_at
        active_task["prompt"] = matched.prompt or active_task.get("prompt") or ""
        active_task["request_meta"] = matched.request_meta or active_task.get("request_meta")
        if active_task.get("status") != matched.status:
            active_task["status"] = matched.status

    if running:
        active_task["status"] = "running"
    elif matched is None and active_task.get("status") == "running":
        active_task["status"] = "ended"
    elif matched is not None and matched.status == "running" and active_task.get("status") == "running":
        active_task["status"] = "ended"

    if matched is not None and matched.status in {"success", "failed"}:
        active_task["status"] = matched.status
        active_task["pid"] = None

    return matched


def _maybe_notify_task_finish(active_task: dict) -> None:
    status = active_task.get("status")
    log_dir = active_task.get("log_dir")
    if not log_dir or status not in {"success", "failed", "ended"}:
        return

    toast_key = f"{log_dir}:{status}"
    if st.session_state.get("home_last_finish_toast") == toast_key:
        return

    title = TASK_SPECS.get(active_task.get("task_id"), {}).get("title", active_task.get("task_id", "任务"))
    icon = "✅" if status == "success" else "⚠️"
    text = f"{title}已完成" if status == "success" else f"{title}已结束，请查看日志"
    st.toast(text, icon=icon)
    st.session_state["home_last_finish_toast"] = toast_key


def _recent_task_rows(tasks: list[TaskRecord], limit: int = 5) -> pd.DataFrame:
    recent = tasks[:limit]
    return pd.DataFrame(
        {
            "任务": [TASK_SPECS.get((t.request_meta or {}).get("task_id", ""), {}).get("title", t.id) for t in recent],
            "状态": [_task_status_label(t.status) for t in recent],
            "时间": [t.created_at for t in recent],
            "提示词": [_prompt_preview(t.prompt) for t in recent],
            "轮次": [((t.request_meta or {}).get("loop_n") or "-") for t in recent],
        }
    )


def _render_prompt_history(tasks: list[TaskRecord], limit: int = 6) -> None:
    recent = [t for t in tasks if t.prompt][:limit]
    if not recent:
        st.caption("最近任务里还没有记录到提示词。")
        return
    for task in recent:
        title = TASK_SPECS.get((task.request_meta or {}).get("task_id", ""), {}).get("title", task.id)
        with st.expander(f"{title} · {task.created_at} · {_task_status_label(task.status)}", expanded=False):
            st.write(task.prompt)
            meta = task.request_meta or {}
            meta_col1, meta_col2, meta_col3 = st.columns(3)
            meta_col1.metric("轮次", meta.get("loop_n") or "-")
            meta_col2.metric("最长时长", meta.get("all_duration") or "-")
            meta_col3.metric("报告数", len(meta.get("report_files") or []))


@st.cache_data(show_spinner=False, ttl=600)
def _pdf_preview(file_name: str, file_bytes: bytes) -> dict:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page_count = doc.page_count
    first_page = doc.load_page(0)
    preview_text = first_page.get_text("text") or ""
    preview_text = re.sub(r"\s+", " ", preview_text).strip()
    preview_text = preview_text[:900]
    pix = first_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    image_bytes = pix.tobytes("png")
    return {
        "file_name": file_name,
        "page_count": page_count,
        "preview_text": preview_text,
        "image_bytes": image_bytes,
    }


def _render_report_preview_panel(report_items: list[dict], *, panel_title: str = "报告小窗") -> None:
    if not report_items:
        return
    render_section_intro(panel_title, "刷新页面后仍会保留本次会话里上传过的报告预览。")
    selected_name = st.selectbox(
        "选择报告",
        [item["name"] for item in report_items],
        key=f"report_preview_select_{panel_title}",
        label_visibility="collapsed",
    )
    selected_item = next((item for item in report_items if item["name"] == selected_name), report_items[0])
    try:
        preview = _pdf_preview(selected_item["name"], selected_item["content"])
    except Exception as err:
        st.warning(f"{selected_item['name']} 预览失败：{err}")
        return

    meta_col1, meta_col2 = st.columns(2)
    meta_col1.metric("页数", preview["page_count"])
    meta_col2.metric("文件大小", f"{selected_item.get('size', len(selected_item['content'])) / 1024 / 1024:.1f} MB")
    st.image(preview["image_bytes"], caption=f"{selected_item['name']} 首页预览", use_container_width=True)
    if preview["preview_text"]:
        st.caption("首页文本摘录")
        st.write(preview["preview_text"])
    else:
        st.caption("首页未提取到可读文本，可能是扫描版 PDF。")


@st.cache_data(show_spinner=False, ttl=300)
def _build_compare_rows(log_root_str: str, limit: int = 60) -> pd.DataFrame:
    log_root = Path(log_root_str)
    rows = []
    for d in list_log_dirs(log_root)[:limit]:
        s = summarize_log_dir(d)
        p = s.get("perf", {})
        rows.append(
            {
                "任务目录": d.name,
                "任务类型": s.get("task_type_cn", "未知任务"),
                "年化收益": p.get("ann_return"),
                "夏普": p.get("sharpe"),
                "Sortino": p.get("sortino"),
                "Calmar": p.get("calmar"),
                "最大回撤": p.get("max_drawdown"),
                "胜率": p.get("win_rate"),
                "IC_IR": p.get("ic_ir"),
            }
        )
    return pd.DataFrame(rows)

st.set_page_config(page_title="首页 · AlphaFlow", page_icon="🏠", layout="wide")
apply_shared_page_style()

if not st.session_state.get("auth_token"):
    st.switch_page("login.py")

render_app_sidebar("pages/home.py")

log_root = Path(st.session_state.get("log_root", "./log"))
tasks, factors = scan_logs(log_root)
active_task = _get_active_task_state()
active_record = _sync_active_task(active_task, tasks)
_maybe_notify_task_finish(active_task)
render_page_hero(
    "AlphaFlow 工作台",
    "把任务发起、运行观察和结果入口放在同一个页面里，减少来回跳转，更适合日常使用。",
    None,
)

top_col1, top_col2, top_col3, top_col4 = st.columns(4)
top_col1.metric("任务总数", len(tasks))
top_col2.metric("运行中", sum(1 for t in tasks if t.status == "running"))
top_col3.metric("成功任务", sum(1 for t in tasks if t.status == "success"))
top_col4.metric("因子记录", len(factors))

workspace_col, status_col = st.columns([1.65, 1], gap="large")

with workspace_col:
    with st.container(border=True):
        render_section_intro("发起任务", "选择任务类型、补充业务提示词和参数，然后从这里直接启动。")

with status_col:
    with st.container(border=True):
        render_section_intro("当前状态", "先看有没有正在跑的任务，再决定继续发起还是先观察。")
        if active_task.get("task_id"):
            running = active_task.get("status") == "running"
            st.metric("当前任务", TASK_SPECS.get(active_task.get("task_id"), {}).get("title", active_task.get("task_id")))
            st.metric("运行状态", _task_status_label(active_task.get("status")))
            st.metric("PID", active_task.get("pid") or "-")
            st.caption(f"日志目录：{Path(active_task.get('log_dir')).name if active_task.get('log_dir') else '-'}")
            st.checkbox("自动刷新状态（8秒）", key="home_auto_refresh", value=st.session_state.get("home_auto_refresh", True))
        else:
            st.caption("当前没有活动任务。")
            st.info("你可以直接在左侧发起新任务。")

task_options = list(TASK_SPECS.keys())
task_labels = {task_id: f"{spec['title']} · {task_id}" for task_id, spec in TASK_SPECS.items()}
selected_task = st.selectbox(
    "选择任务",
    task_options,
    format_func=lambda x: task_labels.get(x, x),
    index=0,
)
selected_spec = TASK_SPECS[selected_task]
prompt_key = f"prompt_{selected_task}"
report_preview_items: list[dict] = []

with workspace_col:
    st.caption(selected_spec["desc"])
    _render_prompt_guide(selected_spec, prompt_key)
    param_col1, param_col2 = st.columns([2, 1])
    with param_col1:
        prompt_text = st.text_area(
            "任务提示词",
            placeholder=selected_spec.get("prompt_hint", "输入任务提示词"),
            height=120,
            key=prompt_key,
        )
        _render_prompt_quality_hint(prompt_text)
    with param_col2:
        if selected_spec.get("supports_loop"):
            loop_n = st.number_input("循环次数", min_value=1, max_value=50, value=5, step=1, key=f"loop_{selected_task}")
        else:
            loop_n = None
            st.info("该任务按报告数量自动决定轮次。")
        all_duration = st.text_input("最长运行时长", placeholder="如 30m / 2h", key=f"duration_{selected_task}")

uploaded_reports = None
if selected_spec.get("needs_reports"):
    with workspace_col:
        uploaded_reports = st.file_uploader(
            "上传报告 PDF",
            type=["pdf"],
            accept_multiple_files=True,
            help="用于‘因子从报告中读取’任务，将自动从 PDF 中抽取候选因子。",
            key="home_report_uploader",
        )
        report_preview_items = _sync_report_draft(selected_task, uploaded_reports)
        action_col1, action_col2 = st.columns([1, 1])
        with action_col1:
            if report_preview_items:
                st.success(f"已缓存 {len(report_preview_items)} 份报告，刷新页面后仍可继续预览与启动。")
        with action_col2:
            if report_preview_items and st.button("清空报告缓存", use_container_width=True):
                _clear_report_draft(selected_task)
                st.toast("已清空当前任务的报告缓存", icon="🗑️")
                st.rerun()

if selected_spec.get("needs_reports"):
    with status_col:
        with st.container(border=True):
            if not report_preview_items and active_task.get("report_files"):
                report_preview_items = _load_saved_report_items(active_task.get("report_files"))
            if report_preview_items:
                _render_report_preview_panel(report_preview_items)
            else:
                render_section_intro("报告小窗", "上传 PDF 后，这里会固定显示报告预览，不需要每次重新上传。")
                st.caption("当前还没有可预览的报告。")

with workspace_col:
    launch_col1, launch_col2, launch_col3 = st.columns(3)
    with launch_col1:
        if st.button("🟢 启动任务", type="primary", use_container_width=True):
            if selected_spec.get("needs_reports") and not report_preview_items:
                st.warning("该任务需要先上传 PDF 报告。")
            else:
                try:
                    task_info = launch_task(
                        selected_task,
                        log_root=log_root,
                        prompt=prompt_text,
                        loop_n=loop_n,
                        all_duration=all_duration.strip() or None,
                        uploaded_reports=report_preview_items,
                    )
                    st.session_state["home_active_task"] = task_info
                    st.toast(f"{selected_spec['title']} 已启动", icon="🚀")
                    st.success(f"已启动 {selected_spec['title']}，PID={task_info['pid']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"启动失败：{e}")
    with launch_col2:
        if st.button("🟥 停止任务", use_container_width=True, disabled=not active_task.get("pid")):
            stop_task(active_task.get("pid"))
            st.session_state["home_active_task"]["pid"] = None
            st.session_state["home_active_task"]["status"] = "ended"
            st.info("已尝试停止当前任务。")
    with launch_col3:
        if st.button("🔄 刷新状态", use_container_width=True):
            st.toast("已刷新任务状态", icon="🔄")
            st.rerun()
    st.caption("启动为主操作；停止会终止当前后台进程；刷新只重新读取日志与状态。")

if active_task.get("task_id"):
    running = active_task.get("status") == "running"
    with status_col:
        with st.container(border=True):
            render_section_intro("任务日志", "这里保留最常用的状态、命令和日志尾部，方便你边看边调。")
            status_row1, status_row2 = st.columns(2)
            status_row1.metric("当前任务", TASK_SPECS.get(active_task.get("task_id"), {}).get("title", active_task.get("task_id")))
            status_row2.metric("状态", _task_status_label(active_task.get("status")))
            info_col1, info_col2 = st.columns(2)
            info_col1.metric("启动时间", active_task.get("created_at") or "-")
            info_col2.metric("日志状态", _task_status_label(active_record.status if active_record else active_task.get("status")))
            if active_task.get("report_files"):
                with st.expander("已上传报告", expanded=False):
                    st.write(active_task.get("report_files"))
            if (active_task.get("prompt") or "").strip():
                with st.expander("本次提示词", expanded=False):
                    st.write(active_task.get("prompt"))
            with st.expander("启动命令", expanded=False):
                st.code(" ".join(active_task.get("command") or []), language="bash")
            with st.expander("日志尾部", expanded=True):
                tail_text = tail_file(active_task.get("stdout_file"), n=80)
                if tail_text:
                    st.code(tail_text, language="text")
                else:
                    st.caption("日志还没有输出，稍后刷新。")

st.markdown("---")

render_section_intro("运行趋势", "先看整体情况，再决定是继续发起新任务，还是去历史页面做复盘。")
col1, col2, col3, col4 = st.columns(4)
col1.metric("任务总数", len(tasks))
col2.metric("因子记录", len(factors))
col3.metric("成功率", f"{(sum(1 for t in tasks if t.status=='success')/len(tasks)*100):.0f}%" if tasks else "-")
col4.metric("日志目录", str(log_root))

col5, col6, col7, col8 = st.columns(4)
col5.metric("成功任务", sum(1 for t in tasks if t.status == "success"))
col6.metric("失败任务", sum(1 for t in tasks if t.status == "failed"))
col7.metric("运行中", sum(1 for t in tasks if t.status == "running"))
col8.metric("因子产物", sum(len(t.artifacts or []) for t in factors))

st.markdown("---")
bottom_col1, bottom_col2 = st.columns([1.15, 1], gap="large")

with bottom_col1:
    render_section_intro("最近任务", "最近 5 条任务放在这里，便于快速判断当前节奏。")
    if tasks:
        st.dataframe(_recent_task_rows(tasks, limit=5), use_container_width=True, hide_index=True)
        render_section_intro("提示词历史", "保留最近几次从页面发起任务时填写的提示词，方便复盘。")
        _render_prompt_history(tasks, limit=6)
    else:
        st.info("暂无任务记录。")

with bottom_col2:
    render_section_intro("任务对比", "按核心指标做横向比较，帮助你决定下一轮重点。")
    compare_df = _build_compare_rows(str(log_root), limit=80)
    if compare_df.empty:
        st.info("暂无可对比任务数据。")
    else:
        c1, c2 = st.columns([1, 1])
        with c1:
            type_options = ["全部"] + sorted(compare_df["任务类型"].dropna().unique().tolist())
            selected_type = st.selectbox("任务类型", type_options, index=0)
        with c2:
            metric_for_bar = st.selectbox("对比指标", ["夏普", "年化收益", "IC_IR", "最大回撤", "胜率"], index=0)

        filtered = compare_df.copy()
        if selected_type != "全部":
            filtered = filtered[filtered["任务类型"] == selected_type]
        if filtered.empty:
            st.caption("筛选后无数据。")
        else:
            sort_asc = metric_for_bar == "最大回撤"
            filtered = filtered.sort_values(metric_for_bar, ascending=sort_asc).head(6)
            show_df = filtered[["任务目录", "任务类型", metric_for_bar]].copy()
            if metric_for_bar in ["年化收益", "最大回撤", "胜率"]:
                show_df[metric_for_bar] = show_df[metric_for_bar].map(_fmt_pct)
            st.dataframe(show_df, use_container_width=True, hide_index=True)
            if filtered[metric_for_bar].notna().any():
                st.plotly_chart(
                    px.bar(filtered, x="任务目录", y=metric_for_bar, color="任务类型", title=f"{metric_for_bar} 对比"),
                    use_container_width=True,
                )

st.markdown("---")

if active_task.get("task_id") and active_task.get("status") == "running" and st.session_state.get("home_auto_refresh", True):
    time.sleep(8)
    st.rerun()
