"""Utility functions to scan log directory for task and factor records.

This is additive-only and does not alter existing pipelines. It reads log folders,
parses minimal metadata, and can be reused by new UI pages.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Tuple
import json
import re
import time


@dataclass
class TaskRecord:
    id: str
    name: str
    created_at: str
    status: str
    log_dir: Path
    owner: str | None = None
    task_type: str | None = None
    artifacts: list[str] | None = None
    log_file: Path | None = None
    download_files: list[str] | None = None
    request_meta: dict | None = None
    prompt: str | None = None

    def to_dict(self):
        data = asdict(self)
        data["log_dir"] = str(self.log_dir)
        return data


FACTOR_KEYWORDS = ["factor", "fin_factor", "factorfbworkspace", "qlibfactor", "factor_from"]
FACTOR_ARTIFACT_HINTS = [
    "combined_factors_df.parquet",
    "qlib_res.csv",
    "result.h5",
    "quantitative backtesting chart",
]
SUCCESS_HINTS = ["finished", "completed", "done", "save", "success"]
FAIL_HINTS = ["traceback", "error", "failed"]
TASK_TYPE_HINTS = {
    "fin_factor": "factor",
    "factor": "factor",
    "quant": "quant",
    "model": "model",
    "kaggle": "kaggle",
}

DOWNLOAD_FILE_NAMES = [
    "combined_factors_df.parquet",
    "qlib_res.csv",
    "result.h5",
    "submission.csv",
]


def _read_tail(path: Path, n: int = 200) -> list[str]:
    try:
        with path.open("r") as f:
            lines = f.readlines()
        return lines[-n:]
    except Exception:
        return []


def _read_head(path: Path, n: int = 40) -> list[str]:
    try:
        with path.open("r") as f:
            lines = f.readlines()
        return lines[:n]
    except Exception:
        return []


def _detect_status(text: str) -> str:
    lower = text.lower()
    if any(h in lower for h in FAIL_HINTS):
        return "failed"
    if any(h in lower for h in SUCCESS_HINTS):
        return "success"
    return "running"


def _detect_session_stage_status(folder: Path) -> str | None:
    session_root = folder / "__session__"
    if not session_root.exists():
        return None

    step_dirs = [p for p in session_root.rglob("*") if p.is_dir() and re.match(r"^\d+_", p.name)]
    if not step_dirs:
        return None

    step_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest_stage = step_dirs[0].name.lower()

    if latest_stage.endswith("feedback") or latest_stage.endswith("record"):
        return "success"
    if latest_stage.endswith("running"):
        return None
    return None


def _infer_status(folder: Path, text: str, artifacts: list[str]) -> str:
    text_status = _detect_status(text)
    if text_status != "running":
        return text_status

    session_status = _detect_session_stage_status(folder)
    if session_status is not None:
        return session_status

    if artifacts and not (folder / "stdout.log").exists():
        return "success"

    return "running"


def _is_factor_task(name: str, text: str) -> bool:
    lower_name = name.lower()
    lower_text = text.lower()
    return any(k in lower_name or k in lower_text for k in FACTOR_KEYWORDS)


def _is_factor_artifacts(artifacts: list[str]) -> bool:
    if not artifacts:
        return False
    blob = "\n".join(artifacts).lower()
    return any(h in blob for h in FACTOR_ARTIFACT_HINTS)


def _extract_artifacts(folder: Path) -> list[str]:
    exts = {".csv", ".pkl", ".h5", ".png", ".html", ".json"}
    artifacts: list[str] = []
    for p in folder.rglob("*"):
        if p.is_file() and p.suffix in exts:
            try:
                artifacts.append(str(p.relative_to(folder.parent)))
            except Exception:
                artifacts.append(str(p))
    return artifacts


def _workspace_root_candidates(log_root: Path) -> list[Path]:
    repo_root = log_root.parent
    return [
        repo_root / "git_ignore_folder" / "RD-Agent_workspace",
        repo_root / "RD-Agent_workspace",
        repo_root / "workspace_cache",
    ]


def _collect_workspace_download_pool(log_root: Path) -> list[tuple[Path, float]]:
    pool: list[tuple[Path, float]] = []
    for root in _workspace_root_candidates(log_root):
        if not root.exists():
            continue
        for name in DOWNLOAD_FILE_NAMES:
            for fp in root.rglob(name):
                try:
                    pool.append((fp, fp.stat().st_mtime))
                except Exception:
                    continue
    return pool


def _nearest_download_files(download_pool: list[tuple[Path, float]], created_ts: float, topk: int = 8) -> list[str]:
    if not download_pool:
        return []
    ranked = sorted(download_pool, key=lambda x: abs(x[1] - created_ts))
    return [str(p) for p, _ in ranked[:topk]]


def _extract_owner(text: str) -> str | None:
    # simple heuristics to find user/email
    match = re.search(r"user=([\w@.\-]+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"by ([\w@.\-]+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _read_request_meta(folder: Path) -> dict | None:
    meta_file = folder / "task_request.json"
    if not meta_file.exists():
        return None
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _detect_task_type(name: str, text: str) -> str | None:
    lower = f"{name} {text}".lower()
    for k, v in TASK_TYPE_HINTS.items():
        if k in lower:
            return v
    return None


def _prompt_preview(request_meta: dict | None) -> str | None:
    if not request_meta:
        return None
    prompt = (request_meta.get("prompt") or "").strip()
    return prompt or None


def scan_logs(log_root: Path) -> Tuple[List[TaskRecord], List[TaskRecord]]:
    """Scan log_root for task and factor records.

    Returns (tasks, factors), where factors is a subset filtered by factor keywords.
    """
    tasks: list[TaskRecord] = []
    factors: list[TaskRecord] = []

    if not log_root.exists():
        return tasks, factors

    download_pool = _collect_workspace_download_pool(log_root)

    # iterate directories sorted by mtime desc
    dirs = [p for p in log_root.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for d in dirs:
        log_file = d / "stdout.log"
        head = _read_head(log_file)
        tail = _read_tail(log_file)
        text = "\n".join(head + tail)

        created_ts = d.stat().st_mtime
        created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_ts))
        owner = _extract_owner(text)
        request_meta = _read_request_meta(d)
        task_type = _detect_task_type(d.name, text)
        if task_type is None and request_meta:
            task_type = _detect_task_type(str(request_meta.get("task_id", "")), "")
        artifacts = _extract_artifacts(d)
        status = _infer_status(d, text, artifacts)

        record = TaskRecord(
            id=d.name,
            name=d.name,
            created_at=created_at,
            status=status,
            log_dir=d,
            log_file=log_file if log_file.exists() else None,
            artifacts=artifacts,
            owner=owner,
            task_type=task_type,
            download_files=_nearest_download_files(download_pool, created_ts, topk=8),
            request_meta=request_meta,
            prompt=_prompt_preview(request_meta),
        )
        tasks.append(record)

        if _is_factor_task(d.name, text) or _is_factor_artifacts(record.artifacts or []) or record.task_type == "factor":
            factors.append(record)

    return tasks, factors


def format_records(records: Iterable[TaskRecord]) -> list[dict]:
    return [r.to_dict() for r in records]


def list_log_dirs(log_root: Path) -> list[Path]:
    if not log_root.exists():
        return []
    dirs = [p for p in log_root.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs


def read_log_tail(log_dir: Path, n: int = 120) -> str:
    log_file = log_dir / "stdout.log"
    lines = _read_tail(log_file, n=n)
    return "".join(lines)
