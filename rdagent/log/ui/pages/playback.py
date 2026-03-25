import streamlit as st
from pathlib import Path
import plotly.express as px
import pandas as pd
import os
import json
import time
from urllib import request, error
from rdagent.log.ui.utils_logscan import list_log_dirs, read_log_tail
from rdagent.log.ui.results_parser import summarize_log_dir, summarize_replay_sections
from rdagent.log.ui.qlib_report_figure import report_figure
from rdagent.log.ui.page_style import apply_shared_page_style, render_app_sidebar


def _fmt_pct(v):
    if v is None:
        return "-"
    try:
        return f"{float(v):.2%}"
    except Exception:
        return str(v)


def _local_insights(perf: dict, task_type_cn: str) -> list[str]:
    tips = [f"该结果归类为：{task_type_cn}。"]
    sharpe = perf.get("sharpe")
    mdd = perf.get("max_drawdown")
    ic_ir = perf.get("ic_ir")
    win = perf.get("win_rate")
    calmar = perf.get("calmar")
    if sharpe is not None:
        tips.append("夏普较好，可进一步看稳定性。" if sharpe >= 1.0 else "夏普偏低，建议优化信号质量或风险约束。")
    if mdd is not None:
        tips.append("最大回撤可控。" if mdd >= -0.15 else "最大回撤偏大，建议检查仓位和止损机制。")
    if ic_ir is not None:
        tips.append("因子稳定性较强。" if ic_ir >= 1.0 else "IC_IR 偏低，因子稳定性需加强。")
    if win is not None:
        tips.append("胜率较高。" if win >= 0.55 else "胜率一般，可结合盈亏比一起评估。")
    if calmar is not None:
        tips.append("Calmar 较好。" if calmar >= 0.8 else "Calmar 一般，建议回撤管理优先。")
    return tips


def _render_formula(formula: str):
    if not formula:
        return
    text = str(formula).strip()
    if not text:
        return
    if text.startswith("$$") and text.endswith("$$"):
        text = text[2:-2].strip()
    elif text.startswith("$") and text.endswith("$"):
        text = text[1:-1].strip()
    try:
        st.latex(text)
    except Exception:
        st.code(str(formula), language="text")


def _list_children(path: Path) -> list[str]:
    if not path.exists() or not path.is_dir():
        return []
    items = [p.name for p in path.iterdir()]
    items.sort()
    return items


def _build_metric_heatmap_rows(dirs: list[Path], task_type_cn: str, topk: int = 12) -> pd.DataFrame:
    rows = []
    for d in dirs[:80]:
        s = summarize_log_dir(d)
        if task_type_cn and s.get("task_type_cn") != task_type_cn:
            continue
        p = s.get("perf", {})
        rows.append(
            {
                "任务目录": d.name,
                "年化收益": p.get("ann_return"),
                "夏普": p.get("sharpe"),
                "最大回撤": p.get("max_drawdown"),
                "IC_IR": p.get("ic_ir"),
                "胜率": p.get("win_rate"),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "夏普" in df.columns and df["夏普"].notna().any():
        df = df.sort_values("夏普", ascending=False)
    return df.head(topk)


def _collect_code_files(replay: dict) -> list[dict]:
    code_rows: list[dict] = []
    for rd in replay.get("dev_rounds", []) or []:
        loop_id = rd.get("loop")
        evo_id = rd.get("evo")
        for task in rd.get("tasks", []) or []:
            task_name = task.get("task_name", "unknown")
            workspace_path = task.get("workspace_path", "")
            for fname, content in (task.get("files", {}) or {}).items():
                code_rows.append(
                    {
                        "label": f"Loop {loop_id} · Evo {evo_id} · {task_name} · {fname}",
                        "file_name": fname,
                        "task_name": task_name,
                        "workspace_path": workspace_path,
                        "content": content,
                    }
                )
    return code_rows


def _build_ai_prompt(selected: str, summary: dict) -> str:
    perf = summary.get("perf", {})
    scen = summary.get("scenario_struct", {})
    return (
        "你是量化研究助理。请基于以下回放摘要给出中文精炼解读：\n"
        "1) 用3条要点总结表现；\n"
        "2) 给2条可执行优化建议（参数/风控/验证）；\n"
        "3) 如果是因子任务，补充因子稳定性判断；如果是报告任务，补充报告结构建议。\n"
        f"任务目录: {selected}\n"
        f"任务类型: {summary.get('task_type_cn')}\n"
        f"性能指标: {perf}\n"
        f"场景背景: {scen.get('background', '')[:500]}\n"
        f"实验设置: {scen.get('experiment_setting', '')[:500]}\n"
    )


def _call_ai_insight(prompt: str) -> tuple[bool, str]:
    api_key = os.getenv("CSI_AGENT_AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return False, "未配置 AI Key（设置 `CSI_AGENT_AI_API_KEY` 或 `OPENAI_API_KEY`）。"

    base = os.getenv("CSI_AGENT_AI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("CSI_AGENT_AI_MODEL", "deepseek-chat")
    timeout_sec = int(os.getenv("CSI_AGENT_AI_TIMEOUT", "60"))
    max_retries = int(os.getenv("CSI_AGENT_AI_RETRIES", "2"))
    url = base.rstrip("/") + "/chat/completions"

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是严谨的中文量化研究分析助手。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    req = request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    last_err = ""
    for i in range(max_retries + 1):
        try:
            with request.urlopen(req, timeout=timeout_sec) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                return True, content
            last_err = "AI 返回为空。"
        except error.HTTPError as e:
            try:
                msg = e.read().decode("utf-8")
            except Exception:
                msg = str(e)
            last_err = f"AI 调用失败: {msg}"
            break
        except Exception as e:
            last_err = str(e)
        if i < max_retries:
            time.sleep(1.2 * (i + 1))

    if "timed out" in (last_err or "").lower():
        return (
            False,
            "AI 调用超时。可在 `.env` 增加 `CSI_AGENT_AI_TIMEOUT=120`，或减少并发后重试。"
        )
    return False, f"AI 调用异常: {last_err}"

st.set_page_config(page_title="Playback · AlphaFlow", page_icon="🎞️", layout="wide")
apply_shared_page_style()

if not st.session_state.get("auth_token"):
    st.switch_page("pages/login.py")

render_app_sidebar("pages/playback.py")

st.title("🎞️ 结果回放")
st.caption("选择日志目录后，可预览解析结果（指标/曲线/产物）或跳转工作台回放。")

ai_key_ok = bool(os.getenv("CSI_AGENT_AI_API_KEY") or os.getenv("OPENAI_API_KEY"))
st.caption(
    "AI配置状态：" + ("✅ 已配置" if ai_key_ok else "⚠️ 未配置（将仅使用规则解读）")
)

view_style = st.radio(
    "显示风格",
    ["专业分析", "大屏简洁"],
    horizontal=True,
)
detailed_mode = view_style == "专业分析"

st.markdown(
    """
    <style>
        .csi-chip {
            display:inline-block; padding:6px 12px; border-radius:999px;
            border:1px solid rgba(148,163,184,.35); margin-right:8px; margin-bottom:8px;
            background:rgba(30,41,59,.35); font-size:12px;
        }
        .csi-panel {
            border: 1px solid rgba(148,163,184,.25);
            border-radius: 12px;
            padding: 12px 14px;
            background: rgba(15,23,42,.25);
            margin-bottom: 10px;
        }
        .csi-title {
            font-weight: 600;
            margin-bottom: 6px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

log_root = Path(st.session_state.get("log_root", "./log"))
dirs = list_log_dirs(log_root)

if not dirs:
    st.warning(f"未找到日志目录，检查路径：{log_root}")
    st.stop()

options = [d.name for d in dirs]
selected = st.selectbox("选择日志目录", options)

if selected:
    chosen_dir = log_root / selected
    st.session_state["pending_log_path"] = chosen_dir.relative_to(log_root) if log_root.exists() else chosen_dir
    st.markdown(f"已选择：`{selected}`")

    summary = summarize_log_dir(chosen_dir)
    replay = summarize_replay_sections(chosen_dir)

    st.markdown("---")
    task_type = summary.get("task_type") or "unknown"
    task_type_cn = summary.get("task_type_cn", "未知任务")
    st.markdown(
        f"<span class='csi-chip'>任务类型: {task_type_cn}</span><span class='csi-chip'>任务编码: {task_type}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(f"**摘要**：{summary.get('cn_summary', '')}")

    action_col1, action_col2 = st.columns([1, 1])
    with action_col1:
        if st.button("🔄 重新解析当前结果", use_container_width=True):
            st.rerun()
    with action_col2:
        if st.button("🧭 打开原版工作台回放", use_container_width=True):
            st.switch_page("pages/legacy.py")

    tab_overview, tab_research, tab_dev, tab_code, tab_result, tab_advanced = st.tabs(
        ["总览", "研究任务", "开发迭代", "代码", "结果反馈", "高级"]
    )

    with tab_overview:
        perf = summary.get("perf", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("年化收益", _fmt_pct(perf.get("ann_return")))
        c2.metric("夏普", f"{perf.get('sharpe'):.3f}" if perf.get("sharpe") is not None else "-")
        c3.metric("最大回撤", _fmt_pct(perf.get("max_drawdown")))
        c4.metric("IC_IR", f"{perf.get('ic_ir'):.3f}" if perf.get("ic_ir") is not None else "-")

        scen = summary.get("scenario_struct", {})
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("**背景摘要**")
            st.caption((scen.get("background") or "-")[:500])
        with s2:
            st.markdown("**实验设置**")
            st.caption((scen.get("experiment_setting") or "-")[:500])

        st.markdown("**自动解读**")
        for tip in _local_insights(perf, task_type_cn):
            st.caption(f"- {tip}")

        if st.button("🤖 生成 AI 深度解读", use_container_width=False, key="ai_insight_btn"):
            with st.spinner("AI 正在分析...", show_time=True):
                ok, msg = _call_ai_insight(_build_ai_prompt(selected, summary))
            if ok:
                st.write(msg)
            else:
                st.warning(msg)

        series = summary.get("series", {})
        if "equity" in series:
            st.markdown("**净值/收益曲线**")
            st.plotly_chart(px.line(series["equity"], title="Equity / NAV"), use_container_width=True)
        if "drawdown" in series:
            st.markdown("**回撤曲线**")
            st.plotly_chart(
                px.area(series["drawdown"], title="Drawdown", range_y=[series["drawdown"].min(), 0]),
                use_container_width=True,
            )
        ic_series = summary.get("ic_series")
        if ic_series is not None:
            st.plotly_chart(px.line(ic_series, title="IC 时序"), use_container_width=True)

        hm_df = _build_metric_heatmap_rows(dirs, task_type_cn, topk=12)
        if not hm_df.empty:
            st.markdown("**指标热度图（同类任务）**")
            metric_cols = ["年化收益", "夏普", "最大回撤", "IC_IR", "胜率"]
            hm = hm_df.set_index("任务目录")[metric_cols].copy()
            for col in hm.columns:
                hm[col] = pd.to_numeric(hm[col], errors="coerce")
                col_std = hm[col].std(skipna=True)
                if col_std and not pd.isna(col_std):
                    hm[col] = (hm[col] - hm[col].mean(skipna=True)) / col_std
            fig_hm = px.imshow(
                hm.transpose(),
                labels={"x": "任务目录", "y": "指标", "color": "标准化值"},
                aspect="auto",
                title="同类任务指标热度图",
                color_continuous_scale="RdYlGn",
            )
            st.plotly_chart(fig_hm, use_container_width=True)

        groups = summary.get("artifact_groups", {})
        if groups:
            st.markdown("**产物分类统计**")
            st.table({"类型": list(groups.keys()), "数量": [len(v) for v in groups.values()]})

    with tab_research:
        hyps = replay.get("hypotheses", [])
        if hyps:
            st.markdown("**假设记录**")
            for i, h in enumerate(hyps[-12:], 1):
                with st.expander(f"假设 {i}", expanded=False):
                    st.markdown(f"- **假设**: {h.get('hypothesis','')}")
                    st.markdown(f"- **理由**: {h.get('reason','')}")

        r_tasks = replay.get("research_tasks", [])
        if r_tasks:
            st.markdown("**任务定义（含公式/变量）**")
            for i, task in enumerate(r_tasks[-16:], 1):
                with st.expander(f"任务 {i}: {task.get('task_name','unknown')}", expanded=False):
                    st.markdown(f"- **类型**: {task.get('task_type','')}")
                    st.markdown(f"- **描述**: {task.get('description','')}")
                    if task.get("formula"):
                        st.markdown("- **公式**")
                        _render_formula(task.get("formula"))
                    if task.get("variables"):
                        st.markdown("- **变量**")
                        st.json(task.get("variables"))
        if not hyps and not r_tasks:
            st.info("未读取到研究阶段信息。")

    with tab_dev:
        dev_rounds = replay.get("dev_rounds", [])
        if dev_rounds:
            round_names = [f"Loop {r.get('loop')} · Evo {r.get('evo')}" for r in dev_rounds]
            rtabs = st.tabs(round_names)
            for idx, rd in enumerate(dev_rounds):
                with rtabs[idx]:
                    tasks = rd.get("tasks", [])
                    if not tasks:
                        st.caption("该轮暂无任务。")
                        continue
                    for j, t in enumerate(tasks, 1):
                        fb = t.get("feedback") or {}
                        badge = "✅" if fb.get("final_decision") else "❌"
                        with st.expander(f"任务 {j} {badge} · {t.get('task_name','unknown')}", expanded=False):
                            st.caption(f"workspace: {t.get('workspace_path','')}")
                            if t.get("description"):
                                st.markdown(f"**任务描述**\n\n{t.get('description')}")
                            if t.get("formula"):
                                st.markdown("**公式**")
                                _render_formula(t.get("formula"))
                            if t.get("variables"):
                                st.markdown("**变量**")
                                st.json(t.get("variables"))
                            files = t.get("files", {}) or {}
                            for fname, content in list(files.items())[:10]:
                                with st.expander(f"代码: {fname}", expanded=False):
                                    st.code(content, language="python")
                            if fb.get("final_feedback"):
                                st.markdown("**最终反馈**")
                                st.markdown(str(fb.get("final_feedback")))
                            if fb.get("code_feedback"):
                                st.markdown("**代码反馈**")
                                st.markdown(str(fb.get("code_feedback")))
                            if fb.get("value_feedback"):
                                st.markdown("**数值反馈**")
                                st.markdown(str(fb.get("value_feedback")))
                            if fb.get("shape_feedback"):
                                st.markdown("**形状反馈**")
                                st.markdown(str(fb.get("shape_feedback")))
                            if fb.get("execution_feedback"):
                                st.markdown("**执行反馈日志**")
                                st.code(str(fb.get("execution_feedback")), language="text")
        else:
            st.info("未解析到开发迭代明细。")

    with tab_code:
        code_files = _collect_code_files(replay)
        if not code_files:
            st.info("当前回放里没有解析到代码文件。")
        else:
            selected_code = st.selectbox("选择代码文件", [row["label"] for row in code_files])
            selected_row = next(row for row in code_files if row["label"] == selected_code)
            meta_col1, meta_col2 = st.columns([2, 3])
            with meta_col1:
                st.caption(f"文件：{selected_row['file_name']}")
                st.caption(f"任务：{selected_row['task_name']}")
            with meta_col2:
                if selected_row.get("workspace_path"):
                    st.caption(f"workspace: {selected_row['workspace_path']}")
            st.code(selected_row.get("content") or "", language="python")

    with tab_result:
        if replay.get("backtest_charts"):
            st.markdown("**收益率 / 回测图**")
            chart_obj = replay["backtest_charts"][-1]
            try:
                fig = report_figure(chart_obj)
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.warning(f"回测图渲染失败：{e}")

        fbs = replay.get("hypothesis_feedback", [])
        if fbs:
            st.markdown("**假设反馈**")
            for i, fb in enumerate(fbs[-10:], 1):
                with st.expander(f"反馈 {i}", expanded=False):
                    st.markdown(f"- **观察**: {fb.get('observations','')}")
                    st.markdown(f"- **假设评估**: {fb.get('hypothesis_evaluation','')}")
                    st.markdown(f"- **新假设**: {fb.get('new_hypothesis','')}")
                    st.markdown(f"- **决策**: {fb.get('decision','')}")
                    st.markdown(f"- **理由**: {fb.get('reason','')}")

        if replay.get("runner_results"):
            rr = replay["runner_results"][-1]
            st.markdown("**Runner 输出摘要**")
            st.caption(f"workspace: {rr.get('workspace_path','')}")
            if rr.get("stdout"):
                with st.expander("stdout", expanded=False):
                    st.code(str(rr.get("stdout"))[-6000:], language="text")

        tail = read_log_tail(chosen_dir, n=80)
        if tail:
            with st.expander("日志尾部", expanded=False):
                st.code(tail, language="text")

    with tab_advanced:
        st.caption("多任务对比已迁移到 `home.py`，用于团队总览和横向评估。")
        if replay.get("errors"):
            st.markdown("**解析告警**")
            for err in replay.get("errors", []):
                st.caption(f"- {err}")
        if detailed_mode:
            st.markdown("**扫描记录**")
            for n in summary.get("notes", []):
                st.caption(f"- {n}")
            with st.expander("runner result 对象", expanded=False):
                st.write(summary.get("runner_obj"))
            with st.expander("Qlib 执行日志对象", expanded=False):
                st.write(summary.get("qlib_obj"))
            with st.expander("回测图表对象", expanded=False):
                st.write(summary.get("chart_obj"))
            with st.expander("时间信息对象", expanded=False):
                st.write(summary.get("time_obj"))
            with st.expander("场景对象/摘要", expanded=False):
                st.write(summary.get("scenario_preview", summary.get("scenario_obj")))
        else:
            st.caption("当前为“大屏简洁”模式；切换到“专业分析”可查看底层对象。")

