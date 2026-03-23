from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


TASK_SPECS = {
    "fin_factor": {
        "title": "因子挖掘",
        "desc": "自动生成与演化金融因子",
        "module": "rdagent.app.qlib_rd_loop.factor",
        "needs_reports": False,
        "supports_loop": True,
        "prompt_hint": "输入因子研究方向、市场假设或希望挖掘的信号。",
        "prompt_guide": {
            "good_for": "限定研究方向、约束因子风格、说明优先级，不要直接写代码实现细节。",
            "template": "目标市场/资产 + 想挖掘的信号 + 偏好风格 + 约束条件 + 不要做什么",
            "how_to": [
                "先说清楚研究对象，例如 A股日频、某类资产或某类市场状态。",
                "再描述你想挖掘的信号方向，比如量价、资金流、反转、景气度。",
                "补充优先级和约束，例如先做简单因子、限制候选数量、避免黑盒。",
            ],
            "can_try": [
                "指定偏好的因子风格：可解释、稳健、低相关、简单优先。",
                "指定淘汰条件：不要高重复、不要依赖难获取数据、不要过复杂组合。",
                "指定本轮目标：先扩库、先验证某方向、先做小步快跑。",
            ],
            "avoid": [
                "不要直接写成代码实现指令，例如‘用 pandas 写 rolling 20’。",
                "不要同时塞太多互相冲突的目标，比如既要高创新又只允许极简。",
                "不要只写一个词，例如‘量价’、‘反转’，信息太少。",
            ],
            "examples": [
                "面向A股日频，优先挖掘成交量与资金流共振因子，先做简单可解释因子，避免过强机器学习黑盒。",
                "聚焦中短期反转，优先使用价格与换手率构造因子，控制高相关重复表达，先做3个以内候选因子。",
            ],
        },
    },
    "fin_factor_report": {
        "title": "因子从报告中读取",
        "desc": "上传研报 PDF，自动抽取候选因子并验证",
        "module": "rdagent.app.qlib_rd_loop.factor_from_report",
        "needs_reports": True,
        "supports_loop": False,
        "prompt_hint": "输入报告主题、筛选偏好或你关心的因子方向。",
        "prompt_guide": {
            "good_for": "告诉系统如何筛选研报里的候选因子，例如偏好的主题、风格、复杂度和淘汰条件。",
            "template": "关注主题 + 保留标准 + 排除标准 + 输出偏好",
            "how_to": [
                "先说明你关注哪类研报主题，例如盈利预期、景气度、量价结构。",
                "再写保留标准，例如公式清晰、可日频实现、解释性强。",
                "最后补排除项，例如纯事件点评、需要另类数据、难落地表达。",
            ],
            "can_try": [
                "要求优先保留简单、稳定、可回测的候选因子。",
                "要求偏向某类风格，如基本面、量价结合、预期差。",
                "要求输出更聚焦，比如只要中低复杂度因子。",
            ],
            "avoid": [
                "不要让系统‘总结整篇报告’，这里更适合写筛选标准。",
                "不要只写‘提取所有因子’，这样没有筛选价值。",
                "不要加入与报告内容无关的底层实现细节。",
            ],
            "examples": [
                "优先提取高频景气度、盈利预期修正相关因子，保留可日频实现且公式清晰的因子，忽略纯事件点评。",
                "只保留基本面+量价结合的中低复杂度因子，优先可解释性强的表达，排除需要难以获取另类数据的方案。",
            ],
        },
    },
    "fin_model": {
        "title": "模型开发",
        "desc": "构建与优化预测模型",
        "module": "rdagent.app.qlib_rd_loop.model",
        "needs_reports": False,
        "supports_loop": True,
        "prompt_hint": "输入模型目标、特征方向、风险约束等。",
        "prompt_guide": {
            "good_for": "限定模型研发方向、结构偏好和训练约束，不建议直接指定底层代码写法。",
            "template": "任务目标 + 模型偏好/禁用项 + 数据特征特性 + 训练约束",
            "how_to": [
                "先写你希望优化什么，例如稳定性、泛化、收益或回撤表现。",
                "再说明模型方向偏好，比如时序模型、轻量结构、先调参后换结构。",
                "最后补限制条件，例如参数规模、训练稳定性、禁用某类模型。",
            ],
            "can_try": [
                "要求先从轻量模型开始，避免一次上复杂结构。",
                "要求优先优化超参数或训练稳定性。",
                "要求明确禁用项，如不要 GNN、不要过深网络。",
            ],
            "avoid": [
                "不要把提示词写成完整网络代码。",
                "不要同时要求很多互斥结构，比如既只要极简又要求高度创新。",
                "不要只说‘做个好模型’，缺少目标和约束。",
            ],
            "examples": [
                "目标提升日频选股稳定性，优先时序模型，控制参数规模，避免过深网络和GNN。",
                "优先尝试轻量GRU/LSTM并关注泛化，若训练不稳定可先从超参数而非复杂结构入手。",
            ],
        },
    },
    "fin_quant": {
        "title": "量化策略",
        "desc": "端到端策略研发闭环",
        "module": "rdagent.app.qlib_rd_loop.quant",
        "needs_reports": False,
        "supports_loop": True,
        "prompt_hint": "输入策略目标、风格偏好、收益回撤要求等。",
        "prompt_guide": {
            "good_for": "告诉系统本轮更偏向因子还是模型风格、收益/回撤目标和整体策略倾向。",
            "template": "收益目标 + 风格偏好 + 风险约束 + 优先探索方向",
            "how_to": [
                "先说本轮更看重什么，例如年化、稳健性、低回撤或探索新方向。",
                "再说明风格倾向，例如先因子后模型、先稳健后进攻。",
                "最后补切换规则，例如某方向连续失败后允许转向。",
            ],
            "can_try": [
                "规定本轮优先探索因子还是模型。",
                "规定结果容忍度，例如允许小幅牺牲收益换回撤稳定。",
                "规定节奏，例如先可解释，再逐步增加复杂度。",
            ],
            "avoid": [
                "不要把产品目标写成无法验证的空话，比如‘做到最好’。",
                "不要同时要求所有指标都极致最优。",
                "不要忽略风险约束，否则系统会更偏激进探索。",
            ],
            "examples": [
                "追求稳健超额，优先低回撤风格，先从可解释因子入手，再逐步过渡到轻量时序模型。",
                "本轮更关注年化提升，同时限制回撤恶化，若因子方向连续失败可转向模型结构优化。",
            ],
        },
    },
}


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def ensure_log_root(log_root: Path) -> Path:
    log_root.mkdir(parents=True, exist_ok=True)
    return log_root


def build_task_command(task_id: str, loop_n: int | None, all_duration: str | None, report_dir: Path | None) -> list[str]:
    spec = TASK_SPECS[task_id]
    cmd = [sys.executable, "-m", spec["module"]]
    if spec["needs_reports"] and report_dir is not None:
        cmd += ["--report_folder", str(report_dir)]
    if spec["supports_loop"] and loop_n is not None:
        cmd += ["--loop_n", str(loop_n)]
    if all_duration:
        cmd += ["--all_duration", all_duration]
    return cmd


def _save_uploaded_reports(log_dir: Path, uploaded_reports: list[Any] | None) -> tuple[Path | None, list[str]]:
    if not uploaded_reports:
        return None, []
    report_dir = log_dir / "uploads"
    report_dir.mkdir(parents=True, exist_ok=True)
    saved_files: list[str] = []
    for file in uploaded_reports:
        if file is None:
            continue
        if isinstance(file, dict):
            file_name = file.get("name")
            file_bytes = file.get("content")
        else:
            file_name = getattr(file, "name", None)
            file_bytes = file.getvalue() if hasattr(file, "getvalue") else None

        if not file_name or file_bytes is None:
            continue

        target = report_dir / Path(file_name).name
        target.write_bytes(file_bytes)
        saved_files.append(str(target))
    return report_dir, saved_files


def _write_request_meta(
    log_dir: Path,
    *,
    task_id: str,
    prompt: str,
    loop_n: int | None,
    all_duration: str | None,
    report_files: list[str],
) -> Path:
    meta = {
        "task_id": task_id,
        "prompt": prompt,
        "loop_n": loop_n,
        "all_duration": all_duration,
        "report_files": report_files,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }
    meta_file = log_dir / "task_request.json"
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta_file


def launch_task(
    task_id: str,
    *,
    log_root: Path,
    prompt: str = "",
    loop_n: int | None = None,
    all_duration: str | None = None,
    uploaded_reports: list[Any] | None = None,
) -> dict[str, Any]:
    ensure_log_root(log_root)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_dir = log_root / f"{task_id}_{ts}"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_file = log_dir / "stdout.log"
    created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    report_dir, saved_reports = _save_uploaded_reports(log_dir, uploaded_reports)
    meta_file = _write_request_meta(
        log_dir,
        task_id=task_id,
        prompt=prompt,
        loop_n=loop_n,
        all_duration=all_duration,
        report_files=saved_reports,
    )
    cmd = build_task_command(task_id, loop_n, all_duration, report_dir)
    stdout_handle = stdout_file.open("w")
    proc = subprocess.Popen(
        cmd,
        stdout=stdout_handle,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(get_repo_root()),
        env={
            **os.environ,
            "LOG_TRACE_PATH": str(log_dir),
            "CSI_AGENT_TASK_PROMPT": prompt,
            "CSI_AGENT_TASK_SOURCE": "streamlit_home",
        },
    )
    return {
        "pid": proc.pid,
        "task_id": task_id,
        "log_dir": str(log_dir),
        "stdout_file": str(stdout_file),
        "meta_file": str(meta_file),
        "command": cmd,
        "report_files": saved_reports,
        "prompt": prompt,
        "all_duration": all_duration,
        "loop_n": loop_n,
        "created_at": created_at,
        "status": "running",
    }


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_task(pid: int | None) -> None:
    if not pid:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def tail_file(path: str | Path | None, n: int = 80) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    try:
        lines = p.read_text(errors="ignore").splitlines()
    except Exception:
        return ""
    return "\n".join(lines[-n:])