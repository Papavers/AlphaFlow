import argparse
import hashlib
import json
import re
import textwrap
import time
from collections import defaultdict
from datetime import datetime, timezone
from importlib.resources import files as rfiles
from pathlib import Path
from typing import Callable, Type

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from streamlit import session_state as state
from streamlit_theme import st_theme

from rdagent.components.coder.factor_coder.evaluators import FactorSingleFeedback
from rdagent.components.coder.factor_coder.factor import FactorFBWorkspace, FactorTask
from rdagent.components.coder.model_coder.evaluators import ModelSingleFeedback
from rdagent.components.coder.model_coder.model import ModelFBWorkspace, ModelTask
from rdagent.core.proposal import Hypothesis, HypothesisFeedback
from rdagent.core.scenario import Scenario
from rdagent.log.base import Message
from rdagent.log.storage import FileStorage
from rdagent.log.ui.qlib_report_figure import report_figure
from rdagent.scenarios.general_model.scenario import GeneralModelScenario
from rdagent.scenarios.kaggle.experiment.scenario import KGScenario
from rdagent.scenarios.qlib.experiment.factor_experiment import QlibFactorScenario
from rdagent.scenarios.qlib.experiment.factor_from_report_experiment import (
    QlibFactorFromReportScenario,
)
from rdagent.scenarios.qlib.experiment.model_experiment import (
    QlibModelExperiment,
    QlibModelScenario,
)
from rdagent.scenarios.qlib.experiment.quant_experiment import QlibQuantScenario

st.set_page_config(layout="wide", page_title="CSI_Agent", page_icon="📈", initial_sidebar_state="expanded")

# ===== UI-only translation config (hardcoded) =====
# NOTE: This does NOT change any backend/business logic. It only affects UI display.
TRANSLATION_BASE_URL = "https://api.deepseek.com/v1"
TRANSLATION_MODEL = "deepseek-chat"
TRANSLATION_API_KEY = "sk-be468c9449794795ac3df1155c632246"

# Inject Custom CSS for a fresh, gallery-friendly UI
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --bg: #0f172a;
        --card: #0b1220;
        --muted: #94a3b8;
        --accent: #38bdf8;
        --accent-2: #a5b4fc;
        --border: #1e293b;
        --shadow: 0 18px 40px -24px rgba(0,0,0,0.6);
    }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        color: #e2e8f0;
        background: radial-gradient(circle at 20% 20%, rgba(56,189,248,0.08), transparent 25%),
                    radial-gradient(circle at 80% 10%, rgba(165,180,252,0.1), transparent 22%),
                    radial-gradient(circle at 50% 80%, rgba(56,189,248,0.06), transparent 18%),
                    #0b1220;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}

    [data-testid="stHeader"] {
        background: rgba(12,18,32,0.75);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid var(--border);
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b1220 0%, #0f172a 60%, #0b1220 100%);
        border-right: 1px solid var(--border);
        color: #cbd5e1;
    }
    [data-testid="stSidebar"] section { padding-top: 1.5rem; }

    .main .block-container {
        padding-top: 2.5rem;
        padding-bottom: 2.5rem;
        max-width: 1300px;
    }

    /* Cards */
    .csi-card {
        background: linear-gradient(145deg, rgba(15,23,42,0.9), rgba(15,23,42,0.65));
        border: 1px solid var(--border);
        border-radius: 18px;
        box-shadow: var(--shadow);
        padding: 20px 22px;
    }
    .csi-card + .csi-card { margin-top: 18px; }

    /* Hero */
    .csi-hero {
        background: linear-gradient(120deg, rgba(56,189,248,0.08), rgba(165,180,252,0.08)),
                    rgba(15,23,42,0.92);
        border: 1px solid var(--border);
        border-radius: 24px;
        padding: 26px 28px;
        box-shadow: 0 30px 60px -32px rgba(0,0,0,0.55);
    }
    .csi-hero h1 { color: #e2e8f0; margin: 0; font-size: 2.1rem; letter-spacing: -0.02em; }
    .csi-hero p { color: var(--muted); margin: 6px 0 0; }
    .csi-hero .badge {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 6px 10px; border-radius: 999px;
        border: 1px solid var(--border);
        background: rgba(56,189,248,0.08);
        color: #e0f2fe; font-size: 0.9rem;
    }

    /* Section headers */
    .csi-section-title {
        display: flex; align-items: center; gap: 10px; margin: 0 0 12px;
        font-size: 1.1rem; font-weight: 600; color: #e2e8f0;
    }
    .csi-section-line {
        height: 2px; width: 100%; background: linear-gradient(90deg, #38bdf8 0%, rgba(56,189,248,0) 90%);
        margin-bottom: 18px;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 6px; background: transparent; border-bottom: 1px solid var(--border); }
    .stTabs [data-baseweb="tab"] {
        background: rgba(30,41,59,0.5);
        border-radius: 10px 10px 0 0;
        padding: 10px 16px;
        color: #cbd5e1;
        border: 1px solid transparent;
    }
    .stTabs [aria-selected="true"] {
        background: #0b1220 !important;
        color: #38bdf8 !important;
        border-color: var(--border) !important;
        border-bottom-color: #0b1220 !important;
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(90deg, #38bdf8 0%, #6366f1 100%);
        color: #0b1220;
        border: none;
        border-radius: 12px;
        padding: 5px 9px;
        font-size: 0.88rem;
        font-weight: 600;
        box-shadow: 0 12px 30px -18px rgba(99,102,241,0.8);
        transition: transform 0.12s ease, box-shadow 0.12s ease;
    }
    .stButton > button:hover { transform: translateY(-1px); box-shadow: 0 18px 36px -18px rgba(99,102,241,0.9); }
    .stButton > button:active { transform: translateY(0); }

    /* Inputs */
    textarea, input, select { background: rgba(15,23,42,0.75) !important; color: #e2e8f0 !important; border-radius: 12px !important; border: 1px solid var(--border) !important; }
    label, .stTextArea label { color: #cbd5e1 !important; }

    /* Sidebar toggles: make labels readable on dark bg */
    [data-testid="stSidebar"] [data-testid="stToggle"] label,
    [data-testid="stSidebar"] [data-testid="stToggle"] span {
        color: #e2e8f0 !important;
    }

    /* Tables */
    .stDataFrame, .stTable { border-radius: 12px; border: 1px solid var(--border); box-shadow: var(--shadow); }

    /* Images grid-friendly */
    .csi-image-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
    .csi-image-grid img { width: 100%; height: 200px; object-fit: cover; border-radius: 12px; border: 1px solid var(--border); box-shadow: var(--shadow); }

    /* Markdown links for anchors */
    a[href^="#_"] { text-decoration: none; color: #cbd5e1; }

    /* Small helper text */
    .csi-meta { color: var(--muted); font-size: 0.95rem; }

    /* Horizontal chips for stats */
    .chip-row { display: flex; flex-wrap: wrap; gap: 8px; }
    .chip { padding: 8px 12px; border-radius: 999px; border: 1px solid var(--border); background: rgba(148,163,184,0.08); color: #e2e8f0; font-weight: 500; }

    /* Animations */
    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes borderGlow {
        0%, 100% { border-color: var(--border); box-shadow: 0 0 0 rgba(56,189,248,0); }
        50% { border-color: #38bdf8; box-shadow: 0 0 16px rgba(56,189,248,0.6); }
    }
    @keyframes splashFade {
        0% { opacity: 1; }
        75% { opacity: 1; }
        100% { opacity: 0; visibility: hidden; }
    }
    .fade-in { animation: fadeInUp 0.6s ease-out forwards; }
    .chip:hover, .csi-task-card:hover { animation: borderGlow 1.2s ease-in-out infinite; cursor: pointer; }

    /* Spotlight effect on hover */
    .csi-card:hover, .csi-task-card:hover {
        background: radial-gradient(circle at var(--mouse-x, 50%) var(--mouse-y, 50%), rgba(56,189,248,0.12), rgba(15,23,42,0.85) 50%);
        border-color: rgba(56,189,248,0.4);
        transition: border-color 0.3s ease;
    }

    /* Splash screen */
    .splash-screen {
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 9999;
        background: radial-gradient(circle at 50% 40%, rgba(56,189,248,0.15), rgba(11,18,32,0.95) 60%), #0b1220;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        opacity: 1; transition: opacity 0.8s ease; animation: splashFade 2.8s ease forwards; pointer-events: none;
    }
    .splash-screen.hide { opacity: 0; pointer-events: none; }
    .splash-logo { font-size: 3.5rem; font-weight: 700; color: #38bdf8; margin-bottom: 16px; text-shadow: 0 0 40px rgba(56,189,248,0.5); }
    .splash-tagline { font-size: 1.2rem; color: #cbd5e1; margin-bottom: 8px; }
    .splash-desc { font-size: 0.95rem; color: #94a3b8; max-width: 520px; text-align: center; line-height: 1.6; }

    /* Task selection cards */
    .csi-task-card {
        background: linear-gradient(145deg, rgba(15,23,42,0.85), rgba(15,23,42,0.6));
        border: 1px solid var(--border); border-radius: 16px; padding: 18px 20px;
        box-shadow: var(--shadow); transition: all 0.3s ease; cursor: pointer;
    }
    .csi-task-card:hover { transform: translateY(-4px); box-shadow: 0 24px 48px -24px rgba(56,189,248,0.4); }
    .csi-task-card.selected { border-color: #38bdf8; background: linear-gradient(145deg, rgba(56,189,248,0.1), rgba(15,23,42,0.8)); }
    .csi-task-title { font-size: 1.05rem; font-weight: 600; color: #e2e8f0; margin-bottom: 6px; }
    .csi-task-desc { font-size: 0.9rem; color: #94a3b8; }
</style>
""", unsafe_allow_html=True)



# 获取log_path参数
parser = argparse.ArgumentParser(description="RD-Agent Streamlit App")
parser.add_argument("--log_dir", type=str, help="Path to the log directory")
parser.add_argument("--debug", action="store_true", help="Enable debug mode")
args = parser.parse_args()

# 结果目录优先顺序：命令行 --log_dir > 本地 ./log > 无（仅手动输入）
if args.log_dir:
    main_log_path = Path(args.log_dir)
    if not main_log_path.exists():
        st.error(f"结果目录 `{main_log_path}` 不存在!")
        st.stop()
elif Path("./log").exists():
    main_log_path = Path("./log").resolve()
else:
    main_log_path = None


QLIB_SELECTED_METRICS = [
    "IC",
    "1day.excess_return_with_cost.annualized_return",
    "1day.excess_return_with_cost.information_ratio",
    "1day.excess_return_with_cost.max_drawdown",
]

SIMILAR_SCENARIOS = (
    QlibModelScenario,
    QlibFactorScenario,
    QlibFactorFromReportScenario,
    QlibQuantScenario,
    KGScenario,
)


def filter_log_folders(main_log_path):
    """
    Filter and return the log folders relative to the main log path.
    """
    folders = [folder.relative_to(main_log_path) for folder in main_log_path.iterdir() if folder.is_dir()]
    folders = sorted(folders, key=lambda x: x.name)
    return folders


if "log_path" not in state:
    if main_log_path:
        state.log_path = filter_log_folders(main_log_path)[0]
    else:
        state.log_path = None
        st.toast(":red[**请设置结果路径!**]", icon="⚠️")

if "scenario" not in state:
    state.scenario = None

if "fs" not in state:
    state.fs = None

if "msgs" not in state:
    state.msgs = defaultdict(lambda: defaultdict(list))

if "last_msg" not in state:
    state.last_msg = None

if "current_tags" not in state:
    state.current_tags = []

if "lround" not in state:
    state.lround = 0  # RD Loop Round

if "erounds" not in state:
    state.erounds = defaultdict(int)  # Evolving Rounds in each RD Loop

if "e_decisions" not in state:
    state.e_decisions = defaultdict(lambda: defaultdict(tuple))

# Summary Info
if "hypotheses" not in state:
    # Hypotheses in each RD Loop
    state.hypotheses = defaultdict(None)

if "h_decisions" not in state:
    state.h_decisions = defaultdict(bool)

if "metric_series" not in state:
    state.metric_series = []

if "all_metric_series" not in state:
    state.all_metric_series = []

# Factor Task Baseline
if "alpha_baseline_metrics" not in state:
    state.alpha_baseline_metrics = None

if "excluded_tags" not in state:
    state.excluded_tags = []

if "excluded_types" not in state:
    state.excluded_types = []

if "splash_shown" not in state:
    state.splash_shown = False

if "selected_task" not in state:
    state.selected_task = None

if "task_iterations" not in state:
    state.task_iterations = 5

if "ui_translation_enabled" not in state:
    # Keep a single global switch in state for potential future use; currently translation is manual via button.
    state.ui_translation_enabled = True


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _has_substantial_english(text: str) -> bool:
    # Heuristic: mixed CN labels + long EN content should still be translatable.
    if not isinstance(text, str) or not text:
        return False
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    # If English letters are clearly dominant, treat as English-heavy.
    return latin >= max(40, cjk * 3)


def _looks_like_code_or_data(text: str) -> bool:
    # Avoid translating code blocks / stack traces / tabular dumps.
    if "```" in text:
        return True
    if "Traceback" in text or "Exception" in text:
        return True
    if "def " in text or "class " in text:
        return True
    return False


def _extract_translation_from_messy_output(raw: str) -> str | None:
    """Extract {"translation": "..."} from a verbose model output.

    Some local models ignore formatting constraints and emit analysis + a JSON snippet.
    We conservatively scan for JSON objects and return the first valid `translation` string.
    """

    if not isinstance(raw, str):
        return None

    s = raw.strip()
    if not s:
        return None

    # Fast path: whole string is JSON.
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and isinstance(obj.get("translation"), str):
            return obj["translation"].strip()
    except Exception:
        pass

    # Slow path: scan for JSON objects inside the text.
    # Limit scan length to avoid quadratic blow-ups on extremely long outputs.
    scan = s[:20000]
    n = len(scan)
    for start in range(n):
        if scan[start] != "{":
            continue
        depth = 0
        in_str = False
        escape = False
        for end in range(start, n):
            ch = scan[end]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            else:
                if ch == '"':
                    in_str = True
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = scan[start : end + 1]
                        try:
                            obj = json.loads(candidate)
                            if isinstance(obj, dict) and isinstance(obj.get("translation"), str):
                                return obj["translation"].strip()
                        except Exception:
                            pass
                        break
        # continue scanning for next '{'
    return None


def _translate_markdown_to_zh(
    text: str,
) -> str:
    if not text.strip():
        return text
    system_prompt = (
        "你是一个专业的中英翻译与本地化助手。\n"
        "请把用户提供的英文内容翻译成简体中文。\n"
        "严格要求：\n"
        "- 保持 Markdown 结构不变（标题/列表/表格/链接）。\n"
        "- 保留代码块与行内代码（```...``` 与 `...`）内容，不要翻译其中的代码。\n"
        "- 保留 LaTeX 公式（$...$ / $$...$$）内容。\n"
        "- 不要输出任何解释/步骤/分析/寒暄（例如“您好”）。\n"
        "输出格式要求（必须严格遵守）：\n"
        "- 只输出一个 JSON 对象（不要 Markdown、不要额外文本）。\n"
        "- JSON 只包含一个字段：translation（字符串）。\n"
        "示例：{\"translation\": \"...\"}"
    )
    user_prompt = text

    # UI-only call to a hardcoded OpenAI-compatible endpoint.
    base_url = (TRANSLATION_BASE_URL or "").strip().rstrip("/")
    if base_url.endswith("/v1/models"):
        base_url = base_url[: -len("/models")]
    elif base_url.endswith("/models"):
        base_url = base_url[: -len("/models")]
    if base_url and not base_url.endswith("/v1"):
        base_url = base_url + "/v1"

    import requests

    url = f"{base_url}/chat/completions" if base_url else "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if (TRANSLATION_API_KEY or "").strip():
        headers["Authorization"] = f"Bearer {TRANSLATION_API_KEY.strip()}"

    payload = {
        "model": (TRANSLATION_MODEL or "Llama"),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }

    # Light retry/backoff for transient gateway issues.
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code in (429, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}: {resp.text}", response=resp)
            resp.raise_for_status()
            data = resp.json()
            content = None
            try:
                content = data["choices"][0]["message"]["content"]
            except Exception:
                content = None
            if isinstance(content, str):
                raw = content.strip()
                extracted = _extract_translation_from_messy_output(raw)
                return extracted if extracted else (raw or text)
            return text
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(0.6 * (2**attempt))
                continue
            break
    # Graceful degradation: if the translation endpoint keeps failing (e.g., 5xx like 502),
    # do not crash the UI—just fall back to the original text.
    return text


def render_generated_markdown(text: str, *, key: str, default_is_markdown: bool = True) -> None:
    """UI-only bilingual rendering for generated content."""

    if not isinstance(text, str):
        st.write(text)
        return

    # Simplified UX: always show original text; per-block manual translate button.

    def _render(md: str) -> None:
        if default_is_markdown:
            st.markdown(md)
        else:
            st.write(md)

    # Stable per-block suffix to avoid duplicate Streamlit keys when the same `key`
    # is used multiple times within a single rerun (e.g., per-task feedback).
    suffix = hashlib.sha1(f"{key}\n{text}".encode("utf-8", errors="ignore")).hexdigest()[:10]

    # Manual translation cache per-block (session only).
    translated_key = f"ui_translation::{key}::{suffix}"
    zh_text: str | None = None
    if translated_key in state and isinstance(state[translated_key], str):
        zh_text = state[translated_key]

    can_manual_translate = bool(getattr(state, "ui_translation_enabled", True)) and (not _looks_like_code_or_data(text))

    # Compact right-aligned action.
    if can_manual_translate:
        left, right = st.columns([0.86, 0.14], gap="small")
        with left:
            _render(text)
        with right:
            btn_label = "翻译" if not zh_text else "重译"
            if st.button(btn_label, key=f"{key}__translate_btn__{suffix}"):
                with st.spinner("翻译中..."):
                    try:
                        zh = _translate_markdown_to_zh(text)
                        if isinstance(zh, str) and zh.strip():
                            state[translated_key] = zh.strip()
                            zh_text = state[translated_key]
                            # If仍为英文且原文英文占比高，提示用户接口可能未返回译文
                            if zh_text == text and _has_substantial_english(text):
                                st.warning("翻译接口未返回中文，已保留原文。请检查 1025 端口服务或重试。")
                    except Exception as e:
                        st.error(f"翻译失败：{type(e).__name__}: {e}")
    else:
        _render(text)

    if zh_text:
        st.markdown("**译文**")
        _render(zh_text)


def should_display(msg: Message):
    for t in state.excluded_tags + ["debug_tpl", "debug_llm"]:
        if t in msg.tag.split("."):
            return False

    if type(msg.content).__name__ in state.excluded_types:
        return False

    return True


def get_msgs_until(end_func: Callable[[Message], bool] = lambda _: True):
    if state.fs:
        while True:
            try:
                msg = next(state.fs)
                if should_display(msg):
                    tags = msg.tag.split(".")
                    if "hypothesis generation" in msg.tag:
                        state.lround += 1

                    # new scenario gen this tags, old version UI not have these tags.
                    msg.tag = re.sub(r"\.evo_loop_\d+", "", msg.tag)
                    msg.tag = re.sub(r"Loop_\d+\.[^.]+", "", msg.tag)
                    msg.tag = re.sub(r"\.\.", ".", msg.tag)

                    # remove old redundant tags
                    msg.tag = re.sub(r"init\.", "", msg.tag)
                    msg.tag = re.sub(r"r\.", "", msg.tag)
                    msg.tag = re.sub(r"d\.", "", msg.tag)
                    msg.tag = re.sub(r"ef\.", "", msg.tag)

                    msg.tag = msg.tag.strip(".")

                    if "evolving code" not in state.current_tags and "evolving code" in tags:
                        state.erounds[state.lround] += 1

                    state.current_tags = tags
                    state.last_msg = msg

                    # Update Summary Info
                    if "runner result" in tags:
                        # factor baseline exp metrics
                        if (
                            isinstance(state.scenario, (QlibFactorScenario, QlibQuantScenario))
                            and state.alpha_baseline_metrics is None
                        ):
                            try:
                                sms = msg.content.based_experiments[0].result
                            except AttributeError:
                                sms = msg.content.based_experiments[0].__dict__["result"]
                            sms = sms.loc[QLIB_SELECTED_METRICS]
                            sms.name = "Alpha Base"
                            state.alpha_baseline_metrics = sms

                        if state.lround == 1 and len(msg.content.based_experiments) > 0:
                            try:
                                sms = msg.content.based_experiments[-1].result
                            except AttributeError:
                                sms = msg.content.based_experiments[-1].__dict__["result"]
                            if sms is not None:
                                if isinstance(
                                    state.scenario,
                                    (
                                        QlibModelScenario,
                                        QlibFactorFromReportScenario,
                                        QlibFactorScenario,
                                        QlibQuantScenario,
                                    ),
                                ):
                                    sms_all = sms
                                    sms = sms.loc[QLIB_SELECTED_METRICS]
                                sms.name = f"Baseline"
                                state.metric_series.append(sms)
                                state.all_metric_series.append(sms_all)

                        # common metrics
                        try:
                            sms = msg.content.result
                        except AttributeError:
                            sms = msg.content.__dict__["result"]
                        if isinstance(
                            state.scenario,
                            (
                                QlibModelScenario,
                                QlibFactorFromReportScenario,
                                QlibFactorScenario,
                                QlibQuantScenario,
                            ),
                        ):
                            sms_all = sms
                            sms = sms.loc[QLIB_SELECTED_METRICS]

                        sms.name = f"Round {state.lround}"
                        sms_all.name = f"Round {state.lround}"
                        state.metric_series.append(sms)
                        state.all_metric_series.append(sms_all)
                    elif "hypothesis generation" in tags:
                        state.hypotheses[state.lround] = msg.content
                    elif "evolving code" in tags:
                        msg.content = [i for i in msg.content if i]
                    elif "evolving feedback" in tags:
                        total_len = len(msg.content)
                        none_num = total_len - len(msg.content)
                        right_num = 0
                        for wsf in msg.content:
                            if wsf.final_decision:
                                right_num += 1
                        wrong_num = len(msg.content) - right_num
                        state.e_decisions[state.lround][state.erounds[state.lround]] = (
                            right_num,
                            wrong_num,
                            none_num,
                        )
                    elif "feedback" in tags and isinstance(msg.content, HypothesisFeedback):
                        state.h_decisions[state.lround] = msg.content.decision

                    state.msgs[state.lround][msg.tag].append(msg)

                    # Stop Getting Logs
                    if end_func(msg):
                        break
            except StopIteration:
                st.toast(":red[**已显示所有结果!**]", icon="🛑")
                break


def refresh(same_trace: bool = False):
    if state.log_path is None:
        st.toast(":red[**请设置结果路径!**]", icon="⚠️")
        return

    if main_log_path:
        state.fs = FileStorage(main_log_path / state.log_path).iter_msg()
    else:
        state.fs = FileStorage(state.log_path).iter_msg()

    # detect scenario
    if not same_trace:
        get_msgs_until(lambda m: isinstance(m.content, Scenario))
        if state.last_msg is None or not isinstance(state.last_msg.content, Scenario):
            st.write(state.msgs)
            st.toast(":red[**未检测到场景信息**]", icon="❗")
            state.scenario = None
        else:
            state.scenario = state.last_msg.content
            # --- CSI_Agent Description Override ---
            # 强制覆盖场景描述，确保旧日志也显示中文界面
            if isinstance(state.scenario, QlibFactorScenario):
                state.scenario._rich_style_description = """
### CSI_Agent: 因子挖掘与迭代演化
#### 📊 [概览](#_summary)
CSI_Agent 能够自动进行**因子挖掘**与**模型迭代**。通过闭环的假设生成、代码实现与回测验证，它能不断自我演化，提升因子的有效性。
#### 🎯 [目标](#_summary)
通过自动化迭代，持续挖掘并优化具有**超额收益 (Alpha)** 的金融因子，构建鲁棒的量化预测模型。
"""
            elif isinstance(state.scenario, QlibFactorFromReportScenario):
                state.scenario._rich_style_description = """
### CSI_Agent: 基于研报的因子挖掘
#### 📊 [概览](#_summary)
CSI_Agent 能够自动从金融研报中提取逻辑，进行**因子挖掘**。通过闭环的假设生成、代码实现与回测验证，它能不断自我演化。
#### 🎯 [目标](#_summary)
快速提取并验证研报中的有效因子，构建鲁棒的因子库。
"""
            elif isinstance(state.scenario, QlibModelScenario):
                state.scenario._rich_style_description = """
### CSI_Agent: 模型迭代演化
#### 📊 [概览](#_summary)
CSI_Agent 自动进行量化金融模型的假设生成、结构优化与回测验证。
#### 🎯 [目标](#_summary)
通过持续的反馈与自我改进，构建更准确、鲁棒的预测模型。
"""
            # --------------------------------------
            st.toast(f":green[**检测到场景信息**] *{type(state.scenario).__name__}*", icon="✅")

    state.msgs = defaultdict(lambda: defaultdict(list))
    state.lround = 0
    state.erounds = defaultdict(int)
    state.e_decisions = defaultdict(lambda: defaultdict(tuple))
    state.hypotheses = defaultdict(None)
    state.h_decisions = defaultdict(bool)
    state.metric_series = []
    state.all_metric_series = []
    state.last_msg = None
    state.current_tags = []
    state.alpha_baseline_metrics = None


def evolving_feedback_window(wsf: FactorSingleFeedback | ModelSingleFeedback):
    if isinstance(wsf, FactorSingleFeedback):
        ffc, efc, cfc, vfc = st.tabs(
            ["**最终反馈🏁**", "执行反馈🖥️", "代码反馈📄", "数值反馈🔢"]
        )
        with ffc:
            render_generated_markdown(wsf.final_feedback, key="factor_final_feedback")
        with efc:
            st.code(wsf.execution_feedback, language="log")
        with cfc:
            render_generated_markdown(wsf.code_feedback, key="factor_code_feedback")
        with vfc:
            render_generated_markdown(wsf.value_feedback, key="factor_value_feedback")
    elif isinstance(wsf, ModelSingleFeedback):
        ffc, efc, cfc, msfc, vfc = st.tabs(
            [
                "**最终反馈🏁**",
                "执行反馈🖥️",
                "代码反馈📄",
                "模型形状反馈📐",
                "数值反馈🔢",
            ]
        )
        with ffc:
            render_generated_markdown(wsf.final_feedback, key="model_final_feedback")
        with efc:
            st.code(wsf.execution_feedback, language="log")
        with cfc:
            render_generated_markdown(wsf.code_feedback, key="model_code_feedback")
        with msfc:
            render_generated_markdown(wsf.shape_feedback, key="model_shape_feedback")
        with vfc:
            render_generated_markdown(wsf.value_feedback, key="model_value_feedback")


def display_hypotheses(hypotheses: dict[int, Hypothesis], decisions: dict[int, bool], success_only: bool = False):
    name_dict = {
        "hypothesis": "CSI_Agent 提出的假设⬇️",
        "concise_justification": "原因如下⬇️",
        "concise_observation": "基于观察⬇️",
        "concise_knowledge": "实践后获得的知识⬇️",
    }
    if success_only:
        shd = {k: v.__dict__ for k, v in hypotheses.items() if decisions[k]}
    else:
        shd = {k: v.__dict__ for k, v in hypotheses.items()}
    df = pd.DataFrame(shd).T

    if "concise_observation" in df.columns and "concise_justification" in df.columns:
        df["concise_observation"], df["concise_justification"] = df["concise_justification"], df["concise_observation"]
        df.rename(
            columns={"concise_observation": "concise_justification", "concise_justification": "concise_observation"},
            inplace=True,
        )
    if "reason" in df.columns:
        df.drop(["reason"], axis=1, inplace=True)
    if "concise_reason" in df.columns:
        df.drop(["concise_reason"], axis=1, inplace=True)

    df.columns = df.columns.map(lambda x: name_dict.get(x, x))
    for col in list(df.columns):
        if all([value is None for value in df[col]]):
            df.drop([col], axis=1, inplace=True)

    def style_rows(row):
        if decisions[row.name]:
            return ["color: green;"] * len(row)
        return [""] * len(row)

    def style_columns(col):
        if col.name != name_dict.get("hypothesis", "hypothesis"):
            return ["font-style: italic;"] * len(col)
        return ["font-weight: bold;"] * len(col)

    # st.dataframe(df.style.apply(style_rows, axis=1).apply(style_columns, axis=0))
    st.markdown(df.style.apply(style_rows, axis=1).apply(style_columns, axis=0).to_html(), unsafe_allow_html=True)


def metrics_window(df: pd.DataFrame, R: int, C: int, *, height: int = 300, colors: list[str] = None):
    fig = make_subplots(rows=R, cols=C, subplot_titles=df.columns)

    def hypothesis_hover_text(h: Hypothesis, d: bool = False):
        color = "green" if d else "black"
        text = h.hypothesis
        lines = textwrap.wrap(text, width=60)
        return f"<span style='color: {color};'>{'<br>'.join(lines)}</span>"

    hover_texts = [
        hypothesis_hover_text(state.hypotheses[int(i[6:])], state.h_decisions[int(i[6:])])
        for i in df.index
        if i != "Alpha Base" and i != "Baseline"
    ]
    if state.alpha_baseline_metrics is not None:
        hover_texts = ["Baseline"] + hover_texts
    for ci, col in enumerate(df.columns):
        row = ci // C + 1
        col_num = ci % C + 1
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[col],
                name=col,
                mode="lines+markers",
                connectgaps=True,
                marker=dict(size=10, color=colors[ci]) if colors else dict(size=10),
                hovertext=hover_texts,
                hovertemplate="%{hovertext}<br><br><span style='color: black'>%{x} Value:</span> <span style='color: blue'>%{y}</span><extra></extra>",
            ),
            row=row,
            col=col_num,
        )
    fig.update_layout(showlegend=False, height=height)

    if state.alpha_baseline_metrics is not None:
        for i in range(1, R + 1):  # 行
            for j in range(1, C + 1):  # 列
                fig.update_xaxes(
                    tickvals=[df.index[0]] + list(df.index[1:]),
                    ticktext=[f'<span style="color:blue; font-weight:bold">{df.index[0]}</span>'] + list(df.index[1:]),
                    row=i,
                    col=j,
                )
    st.plotly_chart(fig)

    from io import BytesIO

    buffer = BytesIO()
    df.to_csv(buffer)
    buffer.seek(0)
    st.download_button(label="下载指标 (csv)", data=buffer, file_name="metrics.csv", mime="text/csv")


def summary_window():
    if isinstance(state.scenario, SIMILAR_SCENARIOS):
        st.markdown('<h2 id="_summary" style="display: flex; align-items: center; gap: 0.5rem;">📊 核心数据总览</h2>', unsafe_allow_html=True)
        st.markdown('<div style="height: 2px; background: linear-gradient(90deg, #3B82F6 0%, #EFF6FF 100%); margin-bottom: 2rem;"></div>', unsafe_allow_html=True)
        if state.lround == 0:
            st.info("尚未开始迭代，暂无数据。")
            return
        
        with st.container():
            col_metric, col_hypo = st.columns([3, 2], gap="medium")
            
            with col_metric:
                st.markdown('<p style="font-weight: 600; font-size: 1.1rem; margin-bottom: 1rem;">📈 演化指标趋势</p>', unsafe_allow_html=True)
                
                if isinstance(state.scenario, QlibFactorScenario) and state.alpha_baseline_metrics is not None:
                    df = pd.DataFrame([state.alpha_baseline_metrics] + state.metric_series[1:])
                elif isinstance(state.scenario, QlibQuantScenario) and state.alpha_baseline_metrics is not None:
                    df = pd.DataFrame([state.alpha_baseline_metrics] + state.metric_series[1:])
                else:
                    df = pd.DataFrame(state.metric_series)
                
                # Filter success only logic
                # ... existing logic for show_true_only ...
                
                if df.shape[0] == 1:
                    st.dataframe(df.iloc[0], use_container_width=True)
                elif df.shape[0] > 1:
                    if df.shape[1] == 1:
                        fig = px.line(df, x=df.index, y=df.columns, markers=True, template="plotly_white")
                        fig.update_layout(
                            xaxis_title="迭代轮次", 
                            yaxis_title="指标得分",
                            margin=dict(l=20, r=20, t=20, b=20),
                            height=350
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        metrics_window(df, 1, 4, height=350, colors=["#3B82F6", "#10B981", "#F59E0B", "#EF4444"])

            with col_hypo:
                st.markdown('<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">'
                            '<p style="font-weight: 600; font-size: 1.1rem; margin: 0;">🏅 演化假设记录</p></div>', unsafe_allow_html=True)
                show_true_only = st.toggle("只看成功的假设", value=False, key="summary_toggle")
                
                display_hypotheses(state.hypotheses, state.h_decisions, show_true_only)

    elif isinstance(state.scenario, GeneralModelScenario):
        st.markdown('<h2 id="_summary" style="display: flex; align-items: center; gap: 0.5rem;">📊 任务执行明细</h2>', unsafe_allow_html=True)
        st.markdown('<div style="height: 2px; background: linear-gradient(90deg, #3B82F6 0%, #EFF6FF 100%); margin-bottom: 2rem;"></div>', unsafe_allow_html=True)
        if len(state.msgs[state.lround]["evolving code"]) > 0:
            ws: list[FactorFBWorkspace | ModelFBWorkspace] = state.msgs[state.lround]["evolving code"][-1].content
            tab_names = [
                w.target_task.factor_name if isinstance(w.target_task, FactorTask) else w.target_task.name
                for w in ws
            ]
            for j in range(len(ws)):
                if state.msgs[state.lround]["evolving feedback"][-1].content[j].final_decision:
                    tab_names[j] += " ✔️"
                else:
                    tab_names[j] += " ❌"

            wtabs = st.tabs(tab_names)
            for j, w in enumerate(ws):
                with wtabs[j]:
                    for k, v in w.file_dict.items():
                        with st.expander(f"📄 查看文件: `{k}`", expanded=False):
                            st.code(v, language="python")

                    evolving_feedback_window(state.msgs[state.lround]["evolving feedback"][-1].content[j])


def tabs_hint():
    st.markdown(
        "<p style='font-size: small; color: #888888;'>你可以使用 ⬅️ ➡️ 或按住 Shift 并滚动鼠标滚轮来浏览标签页🖱️。</p>",
        unsafe_allow_html=True,
    )


def tasks_window(tasks: list[FactorTask | ModelTask]):
    if isinstance(tasks[0], FactorTask):
        st.markdown("**因子任务🚩**")
        tnames = [f.factor_name for f in tasks]
        if sum(len(tn) for tn in tnames) > 100:
            tabs_hint()
        tabs = st.tabs(tnames)
        for i, ft in enumerate(tasks):
            with tabs[i]:
                # st.markdown(f"**Factor Name**: {ft.factor_name}")
                st.markdown(f"**描述**: {ft.factor_description}")
                st.latex("Formulation")
                st.latex(ft.factor_formulation)

                mks = "| 变量 | 描述 |\n| --- | --- |\n"
                if isinstance(ft.variables, dict):
                    for v, d in ft.variables.items():
                        mks += f"| ${v}$ | {d} |\n"
                    st.markdown(mks)

    elif isinstance(tasks[0], ModelTask):
        st.markdown("**模型任务🚩**")
        tnames = [m.name for m in tasks]
        if sum(len(tn) for tn in tnames) > 100:
            tabs_hint()
        tabs = st.tabs(tnames)
        for i, mt in enumerate(tasks):
            with tabs[i]:
                # st.markdown(f"**Model Name**: {mt.name}")
                st.markdown(f"**模型类型**: {mt.model_type}")
                st.markdown(f"**描述**: {mt.description}")
                st.latex("Formulation")
                st.latex(mt.formulation)

                mks = "| 变量 | 描述 |\n| --- | --- |\n"
                if mt.variables:
                    for v, d in mt.variables.items():
                        mks += f"| ${v}$ | {d} |\n"
                    st.markdown(mks)
                st.markdown(f"**训练参数**: {mt.training_hyperparameters}")


def research_window():
    st.markdown('<div class="csi-card">', unsafe_allow_html=True)
    title = "研究🔍" if isinstance(state.scenario, SIMILAR_SCENARIOS) else "研究🔍 (reader)"
    st.markdown(f'<div class="csi-section-title" id="_research">🔍 {title}</div>', unsafe_allow_html=True)
    st.markdown('<div class="csi-section-line"></div>', unsafe_allow_html=True)

    if isinstance(state.scenario, SIMILAR_SCENARIOS):
        if pim := state.msgs[round]["load_pdf_screenshot"]:
            imgs = [p.content for p in pim][:9]
            cols = st.columns(3)
            for i, img in enumerate(imgs):
                with cols[i % 3]:
                    st.image(img, use_container_width=True)

        if hg := state.msgs[round]["hypothesis generation"]:
            st.markdown("**假设💡**")
            h: Hypothesis = hg[0].content
            render_generated_markdown(
                f"""
- **假设**: {h.hypothesis}
- **理由**: {h.reason}""",
                key="hypothesis_generation",
            )

        if eg := state.msgs[round]["experiment generation"]:
            tasks_window(eg[0].content)

    elif isinstance(state.scenario, GeneralModelScenario):
        c1, c2 = st.columns([2, 3], gap="medium")
        with c1:
            if pim := state.msgs[0]["pdf_image"]:
                imgs = [p.content for p in pim][:9]
                cols = st.columns(2)
                for i, img in enumerate(imgs):
                    with cols[i % 2]:
                        st.image(img, use_container_width=True)

        with c2:
            if mem := state.msgs[0]["load_experiment"]:
                me: QlibModelExperiment = mem[0].content
                tasks_window(me.sub_tasks)

    st.markdown('</div>', unsafe_allow_html=True)


def feedback_window():
    if isinstance(state.scenario, SIMILAR_SCENARIOS):
        st.markdown('<div class="csi-card" id="_feedback">', unsafe_allow_html=True)
        st.markdown('<div class="csi-section-title">📝 反馈</div>', unsafe_allow_html=True)
        st.markdown('<div class="csi-section-line"></div>', unsafe_allow_html=True)

        if state.lround > 0 and isinstance(
            state.scenario,
            (QlibModelScenario, QlibFactorScenario, QlibFactorFromReportScenario, QlibQuantScenario, KGScenario),
        ):
            if fbr := state.msgs[round]["runner result"]:
                try:
                    st.markdown("**工作区路径**")
                    st.markdown(str(fbr[0].content.experiment_workspace.workspace_path))
                    with st.expander("运行输出/结果", expanded=False):
                        st.code(fbr[0].content.stdout, language="bash")
                except Exception as e:
                    st.error(f"显示工作区路径时出错: {str(e)}")
            with st.expander("**配置⚙️**", expanded=False):
                st.markdown(state.scenario.experiment_setting, unsafe_allow_html=True)

        if fb := state.msgs[round]["feedback"]:
            if fbr := state.msgs[round]["Quantitative Backtesting Chart"]:
                st.markdown("**收益率📈**")
                fig = report_figure(fbr[0].content)
                st.plotly_chart(fig, use_container_width=True)
            st.markdown("**假设反馈🔍**")
            h: HypothesisFeedback = fb[0].content
            render_generated_markdown(
                f"""
- **观察**: {h.observations}
- **假设评估**: {h.hypothesis_evaluation}
- **新假设**: {h.new_hypothesis}
- **决策**: {h.decision}
- **理由**: {h.reason}""",
                key="hypothesis_feedback",
            )

        if isinstance(state.scenario, KGScenario):
            if fbe := state.msgs[round]["runner result"]:
                submission_path = fbe[0].content.experiment_workspace.workspace_path / "submission.csv"
                st.markdown(
                    f":green[**Exp Workspace**]: {str(fbe[0].content.experiment_workspace.workspace_path.absolute())}"
                )
                try:
                    data = submission_path.read_bytes()
                    st.download_button(
                        label="**Download** submission.csv",
                        data=data,
                        file_name="submission.csv",
                        mime="text/csv",
                    )
                except Exception as e:
                    st.markdown(f":red[**Download Button Error**]: {e}")

        st.markdown('</div>', unsafe_allow_html=True)


def evolving_window():
    title = "开发🛠️" if isinstance(state.scenario, SIMILAR_SCENARIOS) else "开发🛠️ (evolving coder)"
    st.markdown('<div class="csi-card" id="_development">', unsafe_allow_html=True)
    st.markdown(f'<div class="csi-section-title">🛠️ {title}</div>', unsafe_allow_html=True)
    st.markdown('<div class="csi-section-line"></div>', unsafe_allow_html=True)

    # Evolving Status
    if state.erounds[round] > 0:
        st.markdown("**☑️ 演化状态**")
        es = state.e_decisions[round]
        e_status_mks = "".join(f"| {ei} " for ei in range(1, state.erounds[round] + 1)) + "|\n"
        e_status_mks += "|--" * state.erounds[round] + "|\n"
        for ei, estatus in es.items():
            if not estatus:
                estatus = (0, 0, 0)
            e_status_mks += "| " + "🕙<br>" * estatus[2] + "✔️<br>" * estatus[0] + "❌<br>" * estatus[1] + " "
        e_status_mks += "|\n"
        st.markdown(e_status_mks, unsafe_allow_html=True)

    # Evolving Tabs
    if state.erounds[round] > 0:
        if state.erounds[round] > 1:
            evolving_round = st.radio(
                "**🔄️演化轮次**",
                horizontal=True,
                options=range(1, state.erounds[round] + 1),
                index=state.erounds[round] - 1,
                key="show_eround",
            )
        else:
            evolving_round = 1

        ws: list[FactorFBWorkspace | ModelFBWorkspace] = state.msgs[round]["evolving code"][evolving_round - 1].content
        # All Tasks

        tab_names = [
            w.target_task.factor_name if isinstance(w.target_task, FactorTask) else w.target_task.name for w in ws
        ]
        if len(state.msgs[round]["evolving feedback"]) >= evolving_round:
            for j in range(len(ws)):
                if state.msgs[round]["evolving feedback"][evolving_round - 1].content[j].final_decision:
                    tab_names[j] += "✔️"
                else:
                    tab_names[j] += "❌"
        if sum(len(tn) for tn in tab_names) > 100:
            tabs_hint()
        wtabs = st.tabs(tab_names)
        for j, w in enumerate(ws):
            with wtabs[j]:
                # Evolving Code
                st.markdown(f"**工作区路径**: {w.workspace_path}")
                for k, v in w.file_dict.items():
                    with st.expander(f":green[`{k}`]", expanded=False):
                        st.code(v, language="python")

                # Evolving Feedback
                if len(state.msgs[round]["evolving feedback"]) >= evolving_round:
                    evolving_feedback_window(state.msgs[round]["evolving feedback"][evolving_round - 1].content[j])

    st.markdown('</div>', unsafe_allow_html=True)


def sidebar_log_inputs() -> None:
    """侧边栏：结果源与过滤（仅 UI 布局；不改动任何业务逻辑）。"""

    st.markdown('<div class="csi-section-title" style="text-align:center; margin-bottom:10px;">🧰 结果控制台</div>', unsafe_allow_html=True)

    with st.expander("📂 结果来源", expanded=True):
        if main_log_path:
            manually = st.toggle("手动输入", help="手动输入完整路径", key="sidebar_log_manual")
            if manually:
                st.text_input("结果路径", key="log_path", on_change=refresh)
            else:
                folders = filter_log_folders(main_log_path)
                st.selectbox("选择结果", folders, key="log_path", on_change=refresh)
        else:
            st.text_input("结果路径", key="log_path", on_change=refresh)

    with st.expander("🧹 过滤", expanded=False):
        state.excluded_tags = st.multiselect(
            "排除标签",
            options=["debug_tpl", "debug_llm", "observation", "reasoning"],
            default=[],
        )
        state.excluded_types = st.multiselect(
            "排除消息类型",
            options=["Scenario", "Report", "Hypothesis", "Experiment"],
            default=[],
        )

    # 翻译：已改为每段结果旁的“翻译”按钮（按需调用本地接口），不在侧栏堆叠配置项。


def sidebar_loop_controls(debug_available: bool) -> bool:
    """侧边栏：结果加载/循环控制（仅 UI 布局；不改动任何业务逻辑）。"""

    st.markdown('<div class="csi-section-title" style="margin-top: 18px;">⚙️ 结果加载与循环</div>', unsafe_allow_html=True)
    st.markdown('<div class="csi-section-line"></div>', unsafe_allow_html=True)

    st.button("全部加载", on_click=lambda: get_msgs_until(lambda m: False), use_container_width=True, type="primary")
    c1, c2 = st.columns(2, gap="small")
    with c1:
        st.button(
            "下一循环",
            on_click=lambda: get_msgs_until(lambda m: "feedback" in m.tag and "evolving feedback" not in m.tag),
            use_container_width=True,
        )
    with c2:
        st.button("下一步骤", on_click=lambda: get_msgs_until(lambda m: "evolving feedback" in m.tag), use_container_width=True)

    st.button("系统重置", on_click=lambda: refresh(same_trace=True), use_container_width=True)

    debug = False
    if debug_available:
        st.markdown('<div style="height: 8px;"></div>', unsafe_allow_html=True)
        debug = st.toggle("调试模式", value=False)
    return debug


def debug_info_panel() -> None:
    with st.expander(":red[**调试信息**]", expanded=True):
        dcol1, dcol2 = st.columns([1, 3])
        with dcol1:
            st.markdown(
                f"**结果路径**: {state.log_path}\n\n"
                f"**排除标签**: {state.excluded_tags}\n\n"
                f"**排除类型**: {state.excluded_types}\n\n"
                f":blue[**消息 ID**]: {sum(sum(len(tmsgs) for tmsgs in rmsgs.values()) for rmsgs in state.msgs.values())}\n\n"
                f":blue[**轮次**]: {state.lround}\n\n"
                f":blue[**evolving round**]: {state.erounds[state.lround]}\n\n"
            )
        with dcol2:
            if state.last_msg:
                st.write(state.last_msg)
                if isinstance(state.last_msg.content, list):
                    st.write(state.last_msg.content[0])
                elif isinstance(state.last_msg.content, dict):
                    st.write(state.last_msg.content)
                elif not isinstance(state.last_msg.content, str):
                    try:
                        st.write(state.last_msg.content.__dict__)
                    except Exception:
                        st.write(type(state.last_msg.content))


toc = """
## [场景描述📖](#_scenario)
## [总览📊](#_summary)
- [**指标📈**](#_metrics)
- [**假设🏅**](#_hypotheses)
## [研发循环♾️](#_rdloops)
- [**研究🔍**](#_research)
- [**开发🛠️**](#_development)
- [**反馈📝**](#_feedback)
"""
if isinstance(state.scenario, GeneralModelScenario):
    toc = """
## [场景描述📖](#_scenario)
### [总览📊](#_summary)
### [研究🔍](#_research)
### [开发🛠️](#_development)
"""

# Sidebar for quick nav
with st.sidebar:
    sidebar_log_inputs()
    debug = sidebar_loop_controls(debug_available=bool(args.debug))

    st.markdown("---")
    with st.expander("🧭 快速导航", expanded=False):
        st.markdown(
            """
            <div style="display: flex; flex-direction: column; gap: 8px;">
                <a class="chip" href="#_scenario" style="text-align:center;">场景描述</a>
                <a class="chip" href="#_summary" style="text-align:center;">结果总览</a>
                <a class="chip" href="#_rdloops" style="text-align:center;">研发循环</a>
                <a class="chip" href="#_research" style="text-align:center;">研究阶段</a>
                <a class="chip" href="#_development" style="text-align:center;">开发阶段</a>
                <a class="chip" href="#_feedback" style="text-align:center;">反馈评估</a>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown(
    '<div class="csi-meta" style="margin: 6px 0 14px;">左侧栏：结果来源/过滤/加载控制；主页面：结果展示。</div>',
    unsafe_allow_html=True,
)

if state.log_path and state.fs is None:
    refresh()

# Splash screen with fade-in (only shows once, auto-hides)
if not state.splash_shown:
    st.markdown(
        """
        <div class="splash-screen" id="splash">
            <div class="splash-logo fade-in">CSI_Agent 🤖</div>
            <div class="splash-tagline fade-in" style="animation-delay: 0.2s;">自主演化的量化投研实验室</div>
            <div class="splash-desc fade-in" style="animation-delay: 0.4s;">
                围绕<strong>中证指数</strong>，深度闭环<strong>假设生成、策略编码、回测验证、自我反馈</strong>。
                采用 <em>多轮迭代、强化学习风格</em> 的演化范式，让 AI 持续优化因子与模型，拥有工业级的全流程能力。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    state.splash_shown = True

# Always show main control panel
st.markdown('<div class="csi-hero fade-in" style="animation-delay: 0.3s;">', unsafe_allow_html=True)
st.markdown('<h1 style="margin:0;">🤖 CSI_Agent 控制中心</h1>', unsafe_allow_html=True)
st.markdown('<p style="margin:4px 0 0;">专注中证指数量化策略研发，多智能体协同演化系统</p>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

if debug:
    debug_info_panel()

st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)

# Task selection cards
st.markdown('<div class="csi-card fade-in" style="animation-delay: 0.4s;">', unsafe_allow_html=True)
st.markdown('<div class="csi-section-title">🎯 选择 Agent 任务</div>', unsafe_allow_html=True)
st.markdown('<div class="csi-section-line"></div>', unsafe_allow_html=True)

task_cols = st.columns(4, gap="medium")
tasks = [
    {"id": "fin_factor", "title": "因子挖掘", "desc": "自动生成与演化金融因子"},
    {"id": "fin_model", "title": "模型开发", "desc": "构建与优化预测模型"},
    {"id": "fin_quant", "title": "量化策略", "desc": "端到端策略研发闭环"},
    {"id": "kaggle", "title": "Kaggle 竞赛", "desc": "自动化数据科学竞赛"},
]

for i, task in enumerate(tasks):
    with task_cols[i]:
        selected_class = "selected" if state.selected_task == task["id"] else ""
        if st.button(f"{task['title']}", key=f"task_{task['id']}", use_container_width=True):
            state.selected_task = task["id"]
        st.markdown(f'<div class="csi-task-desc">{task["desc"]}</div>', unsafe_allow_html=True)

st.markdown('<div style="height: 16px;"></div>', unsafe_allow_html=True)
state.task_iterations = st.slider("**设置迭代次数**", min_value=1, max_value=20, value=5, step=1)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div style="height: 16px;"></div>', unsafe_allow_html=True)

# Prompt input section
st.markdown('<div class="csi-card fade-in" style="animation-delay: 0.6s;">', unsafe_allow_html=True)
st.markdown("<div class=\"csi-section-title\">✨ 输入提示词或指令</div>", unsafe_allow_html=True)
st.markdown('<div class="csi-section-line"></div>', unsafe_allow_html=True)
task_prompt = st.text_area(
    "输入研究目标或提示词:",
    placeholder="例如：挖掘基于成交量分布的超额收益因子，考虑市场微观结构...",
    height=140,
    label_visibility="collapsed",
    key="main_task_prompt"
)
if st.button("🚀 开始研发", use_container_width=True, type="primary", key="main_start_btn"):
    if task_prompt and state.selected_task:
        st.toast(f"任务 [{state.selected_task}] 已派发，迭代 {state.task_iterations} 轮", icon="🚀")
        st.info(f"**提示词**: {task_prompt}")
    elif not state.selected_task:
        st.warning("请先选择一个 Agent 任务")
    else:
        st.error("请输入提示词")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)


def analyze_task_completion():
    st.header("任务完成分析", divider="orange")

    # Dictionary to store results for all loops
    completion_stats = {}

    # Iterate through all loops
    for loop_round in state.msgs.keys():
        if loop_round == 0:  # Skip initialization round
            continue

        max_evolving_round = state.erounds[loop_round]
        if max_evolving_round == 0:
            continue

        # Track tasks that pass in each evolving round
        tasks_passed_by_round = {}
        cumulative_passed = set()

        # For each evolving round in this loop
        for e_round in range(1, max_evolving_round + 1):
            if len(state.msgs[loop_round]["evolving feedback"]) >= e_round:
                # Get feedback for this evolving round
                feedback = state.msgs[loop_round]["evolving feedback"][e_round - 1].content

                # Count passed tasks and track their indices
                passed_tasks = set()
                for j, task_feedback in enumerate(feedback):
                    if task_feedback.final_decision:
                        passed_tasks.add(j)
                        cumulative_passed.add(j)

                # Store both individual round results and cumulative results
                tasks_passed_by_round[e_round] = {
                    "count": len(passed_tasks),
                    "indices": passed_tasks,
                    "cumulative_count": len(cumulative_passed),
                    "cumulative_indices": cumulative_passed.copy(),
                }

        completion_stats[loop_round] = {
            "total_tasks": len(state.msgs[loop_round]["evolving feedback"][0].content),
            "rounds": tasks_passed_by_round,
            "max_round": max_evolving_round,
        }

    # Display results
    if completion_stats:
        # Add an aggregate view at the top
        st.subheader("🔄 Aggregate Completion Across All Loops")

        # Create summary data for comparison
        summary_data = []
        total_tasks_across_loops = 0
        total_passed_r1 = 0
        total_passed_r3 = 0
        total_passed_r5 = 0
        total_passed_r10 = 0
        total_passed_final = 0

        for loop_round, stats in completion_stats.items():
            total_tasks = stats["total_tasks"]
            total_tasks_across_loops += total_tasks

            # Find data for specific rounds
            r1_passed = stats["rounds"].get(1, {}).get("cumulative_count", 0)
            total_passed_r1 += r1_passed

            # For round 3, use the closest round if exactly 3 doesn't exist
            if 3 in stats["rounds"]:
                r3_passed = stats["rounds"][3]["cumulative_count"]
            elif stats["max_round"] >= 3:
                max_r_below_3 = max([r for r in stats["rounds"].keys() if r <= 3])
                r3_passed = stats["rounds"][max_r_below_3]["cumulative_count"]
            else:
                r3_passed = stats["rounds"][stats["max_round"]]["cumulative_count"] if stats["rounds"] else 0
            total_passed_r3 += r3_passed

            # For round 5, use the closest round if exactly 5 doesn't exist
            if 5 in stats["rounds"]:
                r5_passed = stats["rounds"][5]["cumulative_count"]
            elif stats["max_round"] >= 5:
                max_r_below_5 = max([r for r in stats["rounds"].keys() if r <= 5])
                r5_passed = stats["rounds"][max_r_below_5]["cumulative_count"]
            else:
                r5_passed = stats["rounds"][stats["max_round"]]["cumulative_count"] if stats["rounds"] else 0
            total_passed_r5 += r5_passed

            # For round 10
            if 10 in stats["rounds"]:
                r10_passed = stats["rounds"][10]["cumulative_count"]
            else:
                r10_passed = stats["rounds"][stats["max_round"]]["cumulative_count"] if stats["rounds"] else 0
            total_passed_r10 += r10_passed

            # Final round completion
            final_passed = stats["rounds"][stats["max_round"]]["cumulative_count"] if stats["rounds"] else 0
            total_passed_final += final_passed

            # Add to summary table
            summary_data.append(
                {
                    "Loop": f"Loop {loop_round}",
                    "Total Tasks": total_tasks,
                    "Passed (Round 1)": (
                        f"{r1_passed}/{total_tasks} ({r1_passed/total_tasks:.0%})" if total_tasks > 0 else "N/A"
                    ),
                    "Passed (Round 3)": (
                        f"{r3_passed}/{total_tasks} ({r3_passed/total_tasks:.0%})" if total_tasks > 0 else "N/A"
                    ),
                    "Passed (Round 5)": (
                        f"{r5_passed}/{total_tasks} ({r5_passed/total_tasks:.0%})" if total_tasks > 0 else "N/A"
                    ),
                    "Passed (Final)": (
                        f"{final_passed}/{total_tasks} ({final_passed/total_tasks:.0%})" if total_tasks > 0 else "N/A"
                    ),
                }
            )

        if total_tasks_across_loops > 0:
            summary_data.append(
                {
                    "Loop": "**TOTAL**",
                    "Total Tasks": total_tasks_across_loops,
                    "Passed (Round 1)": f"**{total_passed_r1}/{total_tasks_across_loops} ({total_passed_r1/total_tasks_across_loops:.0%})**",
                    "Passed (Round 3)": f"**{total_passed_r3}/{total_tasks_across_loops} ({total_passed_r3/total_tasks_across_loops:.0%})**",
                    "Passed (Round 5)": f"**{total_passed_r5}/{total_tasks_across_loops} ({total_passed_r5/total_tasks_across_loops:.0%})**",
                    "Passed (Final)": f"**{total_passed_final}/{total_tasks_across_loops} ({total_passed_final/total_tasks_across_loops:.0%})**",
                }
            )

        st.table(pd.DataFrame(summary_data))

        # Summary statistics
        st.markdown("### 📊 Overall Completion Progress:")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                label="After Round 1",
                value=f"{total_passed_r1/total_tasks_across_loops:.0%}",
                help=f"{total_passed_r1}/{total_tasks_across_loops} tasks",
            )
        with col2:
            st.metric(
                label="After Round 3",
                value=f"{total_passed_r3/total_tasks_across_loops:.0%}",
                delta=f"{(total_passed_r3-total_passed_r1)/total_tasks_across_loops:.0%}",
                help=f"{total_passed_r3}/{total_tasks_across_loops} tasks",
            )
        with col3:
            st.metric(
                label="After Round 5",
                value=f"{total_passed_r5/total_tasks_across_loops:.0%}",
                delta=f"{(total_passed_r5-total_passed_r3)/total_tasks_across_loops:.0%}",
                help=f"{total_passed_r5}/{total_tasks_across_loops} tasks",
            )
        with col4:
            st.metric(
                label="Final Completion",
                value=f"{total_passed_final/total_tasks_across_loops:.0%}",
                delta=f"{(total_passed_final-total_passed_r5)/total_tasks_across_loops:.0%}",
                help=f"{total_passed_final}/{total_tasks_across_loops} tasks",
            )

        # Show detailed results by loop
        st.markdown("---")
        st.subheader("Detailed Results by Loop")

        for loop_round, stats in completion_stats.items():
            with st.expander(f"Loop {loop_round} Details"):
                total_tasks = stats["total_tasks"]

                # Create a results table
                data = []
                for e_round in range(1, min(11, stats["max_round"] + 1)):
                    if e_round in stats["rounds"]:
                        round_data = stats["rounds"][e_round]
                        data.append(
                            {
                                "Evolving Round": e_round,
                                "Tasks Passed": f"{round_data['count']}/{total_tasks} ({round_data['count']/total_tasks:.0%})",
                                "Cumulative Passed": f"{round_data['cumulative_count']}/{total_tasks} ({round_data['cumulative_count']/total_tasks:.0%})",
                            }
                        )
                    else:
                        data.append({"Evolving Round": e_round, "Tasks Passed": "N/A", "Cumulative Passed": "N/A"})

                df = pd.DataFrame(data)
                st.table(df)

                st.markdown("### Summary:")
                if 1 in stats["rounds"]:
                    st.markdown(
                        f"- After round 1: **{stats['rounds'][1]['cumulative_count']}/{total_tasks}** tasks passed ({stats['rounds'][1]['cumulative_count']/total_tasks:.0%})"
                    )

                if 3 in stats["rounds"]:
                    st.markdown(
                        f"- After round 3: **{stats['rounds'][3]['cumulative_count']}/{total_tasks}** tasks passed ({stats['rounds'][3]['cumulative_count']/total_tasks:.0%})"
                    )
                elif stats["max_round"] >= 3:
                    max_round_below_3 = max([r for r in stats["rounds"].keys() if r <= 3])
                    st.markdown(
                        f"- After round 3: **{stats['rounds'][max_round_below_3]['cumulative_count']}/{total_tasks}** tasks passed ({stats['rounds'][max_round_below_3]['cumulative_count']/total_tasks:.0%})"
                    )

                if 5 in stats["rounds"]:
                    st.markdown(
                        f"- After round 5: **{stats['rounds'][5]['cumulative_count']}/{total_tasks}** tasks passed ({stats['rounds'][5]['cumulative_count']/total_tasks:.0%})"
                    )
                elif stats["max_round"] >= 5:
                    max_round_below_5 = max([r for r in stats["rounds"].keys() if r <= 5])
                    st.markdown(
                        f"- After round 5: **{stats['rounds'][max_round_below_5]['cumulative_count']}/{total_tasks}** tasks passed ({stats['rounds'][max_round_below_5]['cumulative_count']/total_tasks:.0%})"
                    )

                if 10 in stats["rounds"]:
                    st.markdown(
                        f"- After round 10: **{stats['rounds'][10]['cumulative_count']}/{total_tasks}** tasks passed ({stats['rounds'][10]['cumulative_count']/total_tasks:.0%})"
                    )
                elif stats["max_round"] >= 1:
                    st.markdown(
                        f"- After final round ({stats['max_round']}): **{stats['rounds'][stats['max_round']]['cumulative_count']}/{total_tasks}** tasks passed ({stats['rounds'][stats['max_round']]['cumulative_count']/total_tasks:.0%})"
                    )
    else:
        st.info("No task completion data available.")


if state.scenario is not None:
    # Hero panel
    st.markdown(
        f"""
        <div class="csi-hero">
            <div class="badge">CSI_Agent · Adaptive R&D</div>
            <h1>自主演化量化实验室</h1>
            <p>围绕中证指数的高密度投研闭环，兼顾研究、开发与反馈。</p>
            <div class="chip-row" style="margin-top:10px;">
                <div class="chip">场景: {type(state.scenario).__name__}</div>
                <div class="chip">当前轮次: {state.lround}</div>
                <div class="chip">反馈轮次: {state.erounds[state.lround]}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)

    # Scenario description card
    st.markdown('<div class="csi-card" id="_scenario">', unsafe_allow_html=True)
    theme = st_theme(key="main_theme_provider")
    if theme:
        theme = theme.get("base", "light")
    css = f"""
<style>
    a[href="#_rdloops"], a[href="#_research"], a[href="#_development"], a[href="#_feedback"], a[href="#_scenario"], a[href="#_summary"], a[href="#_hypotheses"], a[href="#_metrics"] {{
        color: {"#cbd5e1" if theme == "light" else "#cbd5e1"};
        text-decoration: none;
        font-weight: 500;
    }}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)
    render_generated_markdown(state.scenario.rich_style_description, key="scenario_description")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div style="height: 32px;"></div>', unsafe_allow_html=True)

    # Summary card
    st.markdown('<div class="csi-card">', unsafe_allow_html=True)
    summary_window()
    st.markdown('</div>', unsafe_allow_html=True)

    if st.toggle("显示任务完成度分析"):
        st.markdown('<div class="csi-card">', unsafe_allow_html=True)
        analyze_task_completion()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div style="height: 32px;"></div>', unsafe_allow_html=True)

    # R&D loops
    if isinstance(state.scenario, SIMILAR_SCENARIOS):
        st.markdown('<div class="csi-section-title" id="_rdloops">♾️ 研发闭环迭代</div>', unsafe_allow_html=True)
        st.markdown('<div class="csi-section-line"></div>', unsafe_allow_html=True)

        if len(state.msgs) > 1:
            r_options = sorted(k for k in state.msgs.keys() if k != 0)
            if r_options:
                default_index = max(0, min(state.lround - 1, len(r_options) - 1))
                round = st.radio(
                    "**选择迭代轮次**",
                    horizontal=True,
                    options=r_options,
                    index=default_index,
                    label_visibility="collapsed",
                )
            else:
                round = 1
        else:
            round = 1

        col_left, col_right = st.columns([1.05, 0.95], gap="large")

        with col_left:
            research_window()
            st.markdown('<div style="height: 18px;"></div>', unsafe_allow_html=True)
            feedback_window()

        with col_right:
            evolving_window()

    elif isinstance(state.scenario, GeneralModelScenario):
        rf_c = st.container()
        d_c = st.container()
        round = 0
        with rf_c:
            research_window()
            feedback_window()
        with d_c:
            evolving_window()
    else:
        st.error("Unknown Scenario!")
        st.stop()


st.markdown("<br><br><br>", unsafe_allow_html=True)
# st.markdown("#### Disclaimer")
# st.markdown(
#     "*This content is AI-generated and may not be fully accurate or up-to-date; please verify with a professional for critical matters.*",
#     unsafe_allow_html=True,
# )
