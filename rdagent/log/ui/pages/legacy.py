import streamlit as st
import runpy
import sys
from pathlib import Path
from rdagent.log.ui.page_style import apply_shared_page_style, render_app_sidebar

st.set_page_config(page_title="AlphaFlow 工作台", page_icon="🧭", layout="wide")
apply_shared_page_style()

render_app_sidebar("pages/legacy.py")

st.title("🧭 AlphaFlow 工作台")
st.caption("在新壳内直接运行原有 Streamlit 页面，逻辑保持不变。")

app_path = Path(__file__).resolve().parent.parent / "app.py"

if not app_path.exists():
    st.error(f"未找到工作台文件: {app_path}")
    st.stop()

st.info("下面加载完整工作台（原 UI）。如遇参数冲突，可单独运行 `streamlit run rdagent/log/ui/app.py`。")

# 防止 argparse 读取到 streamlit 自带参数，暂时清洗 argv
_saved_argv = sys.argv
sys.argv = [sys.argv[0]]
try:
    runpy.run_path(str(app_path), run_name="__main__")
finally:
    sys.argv = _saved_argv
