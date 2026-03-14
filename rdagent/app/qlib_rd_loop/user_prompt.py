from __future__ import annotations

import os


UI_TASK_SOURCE = "streamlit_home"


def get_ui_task_prompt() -> str:
    source = os.environ.get("CSI_AGENT_TASK_SOURCE", "").strip()
    prompt = os.environ.get("CSI_AGENT_TASK_PROMPT", "").strip()
    if source != UI_TASK_SOURCE or not prompt:
        return ""
    return prompt


def build_user_requirement_block(title: str = "User Additional Requirement") -> str:
    prompt = get_ui_task_prompt()
    if not prompt:
        return ""
    return f"\n\n## {title}\n{prompt}"
