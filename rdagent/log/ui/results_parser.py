"""Parse log directory artifacts (pkl) for quick summary.
Best effort only; does not modify existing pipelines.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import re

import pandas as pd
import numpy as np
from rdagent.log.storage import FileStorage

TASK_TYPE_HINTS = {
    "fin_report": "report",
    "report": "report",
    "fin_factor": "factor",
    "factor": "factor",
    "quant": "quant",
    "model": "model",
    "kaggle": "kaggle",
}

TYPE_CN = {
    "report": "报告任务",
    "factor": "因子任务",
    "quant": "量化任务",
    "model": "模型任务",
    "kaggle": "竞赛任务",
    None: "未知任务",
}


def _safe_load_pickle(path: Path) -> Any:
    try:
        with path.open("rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _glob_latest(log_dir: Path, pattern: str) -> Optional[Path]:
    candidates = list(log_dir.glob(pattern))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _extract_metrics(obj: Any) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    if obj is None:
        return metrics
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (int, float)):
                metrics[k] = float(v)
    if hasattr(obj, "items") and not isinstance(obj, dict):
        # pandas Series
        try:
            for k, v in obj.items():
                if isinstance(v, (int, float)):
                    metrics[str(k)] = float(v)
        except Exception:
            pass
    if isinstance(obj, pd.DataFrame):
        try:
            desc = obj.describe().iloc[:, 0].to_dict() if not obj.empty else {}
            for k, v in desc.items():
                if isinstance(v, (int, float)):
                    metrics[str(k)] = float(v)
        except Exception:
            pass
    return metrics


def _maybe_series(obj: Any) -> Optional[pd.Series]:
    # Accept pandas Series or DataFrame first column
    if isinstance(obj, pd.Series):
        return obj
    if isinstance(obj, pd.DataFrame) and not obj.empty:
        try:
            return obj.iloc[:, 0]
        except Exception:
            return None
    return None


def _perf_from_equity(equity: pd.Series) -> Dict[str, float]:
    perf: Dict[str, float] = {}
    if equity is None or equity.empty:
        return perf
    eq = equity.astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    if eq.empty:
        return perf
    returns = eq.pct_change().dropna()
    if not returns.empty:
        perf["ann_return"] = (1 + returns.mean()) ** 252 - 1
        perf["ann_vol"] = returns.std() * np.sqrt(252)
        if perf.get("ann_vol") is not None and perf["ann_vol"] != 0:
            perf["sharpe"] = perf["ann_return"] / perf["ann_vol"]
        downside = returns[returns < 0]
        if not downside.empty:
            downside_vol = downside.std() * np.sqrt(252)
            perf["sortino"] = perf["ann_return"] / downside_vol if downside_vol else np.nan
        perf["win_rate"] = float((returns > 0).mean())
        perf["avg_gain"] = float(returns[returns > 0].mean()) if (returns > 0).any() else np.nan
        perf["avg_loss"] = float(returns[returns < 0].mean()) if (returns < 0).any() else np.nan
        perf["return_skew"] = float(returns.skew()) if len(returns) > 2 else np.nan
        perf["return_kurt"] = float(returns.kurt()) if len(returns) > 3 else np.nan
    # max drawdown
    roll_max = eq.cummax()
    dd = (eq / roll_max - 1).fillna(0)
    perf["max_drawdown"] = dd.min()
    if perf.get("max_drawdown") is not None and perf["max_drawdown"] != 0 and perf.get("ann_return") is not None:
        perf["calmar"] = perf["ann_return"] / abs(perf["max_drawdown"])
    return perf


def _extract_series(obj: Any) -> Dict[str, pd.Series]:
    series_map: Dict[str, pd.Series] = {}
    if obj is None:
        return series_map
    # From dict of arrays/series
    if isinstance(obj, dict):
        for k, v in obj.items():
            s = None
            if isinstance(v, (list, tuple)):
                s = pd.Series(v)
            elif isinstance(v, pd.Series):
                s = v
            elif isinstance(v, pd.DataFrame):
                if not v.empty:
                    s = v.iloc[:, 0]
            if s is not None and len(s) > 1:
                series_map[k] = s
    # Direct series
    s = _maybe_series(obj)
    if s is not None and len(s) > 1:
        series_map["series"] = s
    return series_map


def _extract_ic(obj: Any) -> Optional[pd.Series]:
    if isinstance(obj, pd.DataFrame):
        for col in obj.columns:
            if "ic" in str(col).lower():
                return obj[col]
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "ic" in str(k).lower():
                if isinstance(v, (list, tuple)):
                    return pd.Series(v)
                if isinstance(v, pd.Series):
                    return v
    return None


def _extract_timing(obj: Any) -> Dict[str, Any]:
    timing: Dict[str, Any] = {}
    if isinstance(obj, dict):
        for key in ["total", "elapsed", "duration", "runtime", "start_time", "end_time"]:
            if key in obj:
                timing[key] = obj[key]
    return timing


def _collect_artifacts(log_dir: Path) -> list[str]:
    exts = {".pkl", ".csv", ".png", ".html", ".json", ".txt"}
    artifacts: list[str] = []
    for p in log_dir.rglob("*"):
        if p.is_file() and p.suffix in exts:
            try:
                artifacts.append(str(p.relative_to(log_dir)))
            except Exception:
                artifacts.append(str(p))
    return artifacts


def _detect_task_type(name: str, text: str) -> Optional[str]:
    lower = f"{name} {text}".lower()
    for k, v in TASK_TYPE_HINTS.items():
        if k in lower:
            return v
    return None


def _scenario_text(obj: Any) -> str:
    if obj is None:
        return ""
    attrs = getattr(obj, "__dict__", {})
    candidates = []
    for key in ["_background", "_rich_style_description", "_source_data", "_experiment_setting", "_output_format"]:
        if key in attrs:
            candidates.append(str(attrs[key]))
    return "\n".join(candidates)


def _extract_factor_params(text: str) -> Dict[str, str]:
    params: Dict[str, str] = {}
    if not text:
        return params
    patterns = {
        "窗口(window)": r"window\s*[:=]\s*([\w\-]+)",
        "回看期(lookback)": r"look\s*back|lookback\s*[:=]\s*([\w\-]+)",
        "持有期(holding)": r"holding\s*period\s*[:=]\s*([\w\-]+)",
        "调仓频率(rebalance)": r"rebalance\s*[:=]\s*([\w\-]+)",
    }
    lower = text.lower()
    for key, pattern in patterns.items():
        m = re.search(pattern, lower)
        if m:
            val = m.group(1) if m.groups() else m.group(0)
            params[key] = str(val)
    return params


def _scenario_struct(obj: Any) -> Dict[str, Any]:
    attrs = getattr(obj, "__dict__", {}) if obj is not None else {}
    background = str(attrs.get("_background", ""))
    output_format = str(attrs.get("_output_format", ""))
    strategy = str(attrs.get("_strategy", ""))
    exp_setting = str(attrs.get("_experiment_setting", ""))
    rich_desc = str(attrs.get("_rich_style_description", ""))
    source_data = str(attrs.get("_source_data", ""))
    full_text = "\n".join([background, output_format, strategy, exp_setting, rich_desc, source_data])

    return {
        "background": background[:1200],
        "strategy": strategy[:800],
        "experiment_setting": exp_setting[:800],
        "output_format": output_format[:800],
        "source_data": source_data[:800],
        "factor_params": _extract_factor_params(full_text),
    }


def _final_task_type(log_dir: Path, artifacts: list[str], scenario_obj: Any) -> Optional[str]:
    text_blob = " ".join(artifacts) + " " + _scenario_text(scenario_obj)
    t = _detect_task_type(log_dir.name, text_blob)
    if t:
        return t
    # extra heuristics
    lower = text_blob.lower()
    if "from report" in lower or "report" in lower:
        return "report"
    if "factor" in lower:
        return "factor"
    if "model" in lower:
        return "model"
    return None


def summarize_log_dir(log_dir: Path) -> Dict[str, Any]:
    """Return a summary dict with metrics, timing, artifacts, and raw objects."""
    summary: Dict[str, Any] = {
        "metrics": {},
        "timing": {},
        "artifacts": _collect_artifacts(log_dir),
        "runner_obj": None,
        "qlib_obj": None,
        "chart_obj": None,
        "time_obj": None,
        "scenario_obj": None,
        "notes": [],
        "series": {},
        "perf": {},
        "ic_series": None,
        "task_type": None,
        "task_type_cn": "未知任务",
        "artifact_groups": {},
        "cn_summary": "",
        "scenario_struct": {},
    }

    runner_pkl = _glob_latest(log_dir, "**/runner result/**/*.pkl")
    qlib_pkl = _glob_latest(log_dir, "**/Qlib_execute_log/**/*.pkl")
    chart_pkl = _glob_latest(log_dir, "**/Quantitative Backtesting Chart/**/*.pkl")
    time_pkl = _glob_latest(log_dir, "**/time_info/**/*.pkl")
    scenario_pkl = _glob_latest(log_dir, "**/scenario/**/*.pkl")

    runner_obj = _safe_load_pickle(runner_pkl) if runner_pkl else None
    qlib_obj = _safe_load_pickle(qlib_pkl) if qlib_pkl else None
    chart_obj = _safe_load_pickle(chart_pkl) if chart_pkl else None
    time_obj = _safe_load_pickle(time_pkl) if time_pkl else None
    scenario_obj = _safe_load_pickle(scenario_pkl) if scenario_pkl else None

    summary["runner_obj"] = runner_obj
    summary["qlib_obj"] = qlib_obj
    summary["chart_obj"] = chart_obj
    summary["time_obj"] = time_obj
    summary["scenario_obj"] = scenario_obj
    summary["task_type"] = _final_task_type(log_dir, summary["artifacts"], scenario_obj)
    summary["task_type_cn"] = TYPE_CN.get(summary["task_type"], "未知任务")
    summary["scenario_struct"] = _scenario_struct(scenario_obj)

    # metrics
    metrics: Dict[str, float] = {}
    for obj in [runner_obj, qlib_obj, chart_obj]:
        metrics.update(_extract_metrics(obj))
    summary["metrics"] = metrics

    # series extraction: equity/pnl/nav/ic
    series_map: Dict[str, pd.Series] = {}
    for obj in [runner_obj, qlib_obj, chart_obj]:
        series_map.update(_extract_series(obj))
    # heuristics for equity/nav keys
    equity = None
    for key in ["equity", "nav", "portfolio_value", "cumret", "pnl"]:
        if key in series_map:
            equity = series_map[key]
            break
    # try generic series
    if equity is None and series_map:
        equity = next(iter(series_map.values()))
    if equity is not None:
        summary["series"]["equity"] = equity
        dd = (equity / equity.cummax() - 1).fillna(0)
        summary["series"]["drawdown"] = dd
        summary["perf"].update(_perf_from_equity(equity))

    ic_series = _extract_ic(runner_obj) or _extract_ic(qlib_obj) or _extract_ic(chart_obj)
    if ic_series is not None:
        summary["ic_series"] = ic_series
        summary["perf"]["ic_mean"] = float(ic_series.mean()) if not ic_series.empty else None
        summary["perf"]["ic_std"] = float(ic_series.std()) if not ic_series.empty else None
        if summary["perf"].get("ic_std"):
            summary["perf"]["ic_ir"] = summary["perf"]["ic_mean"] / summary["perf"]["ic_std"] if summary["perf"]["ic_std"] else None

    # artifact grouping by extension
    groups: Dict[str, list[str]] = {}
    for path in summary.get("artifacts", []):
        ext = Path(path).suffix or "misc"
        groups.setdefault(ext, []).append(path)
    summary["artifact_groups"] = groups

    # timing
    if time_obj:
        summary["timing"].update(_extract_timing(time_obj))

    # scenario brief
    if scenario_obj:
        scen_text = _scenario_text(scenario_obj)
        summary["scenario_preview"] = scen_text[:1200] if scen_text else str(getattr(scenario_obj, "__dict__", scenario_obj))[:1200]

    # notes
    for name, path in [
        ("runner", runner_pkl),
        ("qlib", qlib_pkl),
        ("chart", chart_pkl),
        ("time", time_pkl),
        ("scenario", scenario_pkl),
    ]:
        if path:
            summary["notes"].append(f"found {name}: {path.relative_to(log_dir) if path.is_relative_to(log_dir) else path}")
        else:
            summary["notes"].append(f"missing {name} pkl")

    # concise Chinese summary
    perf = summary.get("perf", {})
    bullets = []
    if perf.get("ann_return") is not None:
        bullets.append(f"年化收益: {perf['ann_return']:.2%}")
    if perf.get("ann_vol") is not None:
        bullets.append(f"年化波动: {perf['ann_vol']:.2%}")
    if perf.get("sharpe") is not None:
        bullets.append(f"Sharpe: {perf['sharpe']:.2f}")
    if perf.get("max_drawdown") is not None:
        bullets.append(f"最大回撤: {perf['max_drawdown']:.2%}")
    if perf.get("ic_mean") is not None:
        bullets.append(f"IC均值: {perf['ic_mean']:.3f}")
    if perf.get("ic_ir") is not None:
        bullets.append(f"IC_IR: {perf['ic_ir']:.3f}")
    summary["cn_summary"] = "；".join(bullets) if bullets else "暂未解析出关键指标"

    return summary


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _parse_round_info(tag: str) -> tuple[int | None, int | None]:
    loop = None
    evo = None
    lm = re.search(r"Loop_(\d+)", tag)
    em = re.search(r"evo_loop_(\d+)", tag)
    if lm:
        loop = int(lm.group(1))
    if em:
        evo = int(em.group(1))
    return loop, evo


def _unwrap_feedback_list(content: Any) -> list[Any]:
    if isinstance(content, list):
        return content
    fb_list = _safe_attr(content, "feedback_list", None)
    if isinstance(fb_list, list):
        return fb_list
    maybe_content = _safe_attr(content, "content", None)
    if isinstance(maybe_content, list):
        return maybe_content
    return [content]


def _task_meta(task: Any) -> Dict[str, Any]:
    return {
        "task_name": _safe_attr(task, "factor_name", None)
        or _safe_attr(task, "name", None)
        or "unknown_task",
        "task_type": type(task).__name__,
        "description": _safe_attr(task, "factor_description", None)
        or _safe_attr(task, "description", None)
        or "",
        "formula": _safe_attr(task, "factor_formulation", None)
        or _safe_attr(task, "formulation", None)
        or "",
        "variables": _safe_attr(task, "variables", None) or {},
    }


def summarize_replay_sections(log_dir: Path) -> Dict[str, Any]:
    """Read log messages and extract legacy replay sections.

    This mirrors key blocks in legacy `app.py` result playback:
    hypotheses, feedback, backtest chart, evolving code, and evolving feedback.
    """
    sections: Dict[str, Any] = {
        "scenario_description": "",
        "hypotheses": [],
        "research_tasks": [],
        "hypothesis_feedback": [],
        "runner_results": [],
        "backtest_charts": [],
        "evolving_code_tasks": [],
        "evolving_feedback_tasks": [],
        "dev_rounds": [],
        "errors": [],
    }

    dev_map: Dict[tuple[int | None, int | None], Dict[str, Any]] = {}

    try:
        msgs = list(FileStorage(log_dir).iter_msg())
    except Exception as e:
        sections["errors"].append(f"读取日志消息失败: {e}")
        return sections

    for msg in msgs:
        tag = msg.tag or ""
        content = msg.content
        try:
            if "scenario" in tag and not sections["scenario_description"]:
                rich = _safe_attr(content, "rich_style_description", None) or _safe_attr(content, "_rich_style_description", None)
                if rich:
                    sections["scenario_description"] = str(rich)

            if "hypothesis generation" in tag:
                hypo = {
                    "hypothesis": _safe_attr(content, "hypothesis", ""),
                    "reason": _safe_attr(content, "reason", ""),
                    "concise_observation": _safe_attr(content, "concise_observation", ""),
                    "concise_justification": _safe_attr(content, "concise_justification", ""),
                    "loop": _parse_round_info(tag)[0],
                }
                sections["hypotheses"].append(hypo)

            if "experiment generation" in tag:
                tasks = content if isinstance(content, list) else [content]
                for t in tasks:
                    sections["research_tasks"].append(_task_meta(t))

            if tag.endswith("feedback") and "evolving feedback" not in tag:
                fb = {
                    "observations": _safe_attr(content, "observations", ""),
                    "hypothesis_evaluation": _safe_attr(content, "hypothesis_evaluation", ""),
                    "new_hypothesis": _safe_attr(content, "new_hypothesis", ""),
                    "decision": _safe_attr(content, "decision", None),
                    "reason": _safe_attr(content, "reason", ""),
                }
                if any(v not in (None, "") for v in fb.values()):
                    sections["hypothesis_feedback"].append(fb)

            if "runner result" in tag:
                ws = _safe_attr(content, "experiment_workspace", None)
                ws_path = _safe_attr(ws, "workspace_path", None)
                sections["runner_results"].append(
                    {
                        "tag": tag,
                        "workspace_path": str(ws_path) if ws_path else "",
                        "stdout": _safe_attr(content, "stdout", ""),
                        "result": _safe_attr(content, "result", None),
                    }
                )

            if "Quantitative Backtesting Chart" in tag:
                sections["backtest_charts"].append(content)

            if "evolving code" in tag:
                # content can be list of workspaces
                ws_list = content if isinstance(content, list) else [content]
                loop_i, evo_i = _parse_round_info(tag)
                key = (loop_i, evo_i)
                if key not in dev_map:
                    dev_map[key] = {"loop": loop_i, "evo": evo_i, "tasks": []}
                for w in ws_list:
                    task = _safe_attr(w, "target_task", None)
                    tname = _safe_attr(task, "factor_name", None) or _safe_attr(task, "name", None) or "unknown_task"
                    file_dict = _safe_attr(w, "file_dict", {}) or {}
                    sections["evolving_code_tasks"].append(
                        {
                            "loop": loop_i,
                            "evo": evo_i,
                            "task_name": str(tname),
                            "workspace_path": str(_safe_attr(w, "workspace_path", "")),
                            "files": file_dict,
                            "formula": _safe_attr(task, "factor_formulation", None)
                            or _safe_attr(task, "formulation", None)
                            or "",
                            "variables": _safe_attr(task, "variables", None) or {},
                            "description": _safe_attr(task, "factor_description", None)
                            or _safe_attr(task, "description", None)
                            or "",
                        }
                    )
                    dev_map[key]["tasks"].append(
                        {
                            "task_name": str(tname),
                            "workspace_path": str(_safe_attr(w, "workspace_path", "")),
                            "files": file_dict,
                            "formula": _safe_attr(task, "factor_formulation", None)
                            or _safe_attr(task, "formulation", None)
                            or "",
                            "variables": _safe_attr(task, "variables", None) or {},
                            "description": _safe_attr(task, "factor_description", None)
                            or _safe_attr(task, "description", None)
                            or "",
                            "feedback": None,
                        }
                    )

            if "evolving feedback" in tag:
                fb_list = _unwrap_feedback_list(content)
                loop_i, evo_i = _parse_round_info(tag)
                key = (loop_i, evo_i)
                if key not in dev_map:
                    dev_map[key] = {"loop": loop_i, "evo": evo_i, "tasks": []}

                parsed_fb_items = []
                for fb in fb_list:
                    fb_item = {
                        "loop": loop_i,
                        "evo": evo_i,
                        "final_decision": _safe_attr(fb, "final_decision", None),
                        "final_feedback": _safe_attr(fb, "final_feedback", ""),
                        "execution_feedback": _safe_attr(fb, "execution_feedback", ""),
                        "code_feedback": _safe_attr(fb, "code_feedback", ""),
                        "value_feedback": _safe_attr(fb, "value_feedback", ""),
                        "shape_feedback": _safe_attr(fb, "shape_feedback", ""),
                    }
                    parsed_fb_items.append(fb_item)
                    sections["evolving_feedback_tasks"].append(
                        fb_item
                    )

                # attach feedback by index to corresponding tasks in same loop/evo
                for idx, fb_item in enumerate(parsed_fb_items):
                    if idx < len(dev_map[key]["tasks"]):
                        dev_map[key]["tasks"][idx]["feedback"] = fb_item
                    else:
                        dev_map[key]["tasks"].append(
                            {
                                "task_name": f"task_{idx}",
                                "workspace_path": "",
                                "files": {},
                                "formula": "",
                                "variables": {},
                                "description": "",
                                "feedback": fb_item,
                            }
                        )
        except Exception as e:
            sections["errors"].append(f"解析消息失败 tag={tag}: {e}")

    # materialize sorted dev rounds
    rounds = list(dev_map.values())
    rounds.sort(key=lambda x: ((x.get("loop") is None, x.get("loop") or -1), (x.get("evo") is None, x.get("evo") or -1)))
    sections["dev_rounds"] = rounds

    return sections
