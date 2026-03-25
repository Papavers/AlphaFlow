import streamlit as st
from pathlib import Path
from rdagent.log.ui.utils_logscan import scan_logs, format_records, read_log_tail
from rdagent.log.ui.page_style import apply_shared_page_style, render_app_sidebar

st.set_page_config(page_title="因子记录 · AlphaFlow", page_icon="🧬", layout="wide")
apply_shared_page_style()

if not st.session_state.get("auth_token"):
    st.switch_page("pages/login.py")

render_app_sidebar("pages/factors.py")

st.title("🧬 因子记录")
st.caption("自动扫描 log 中的因子生成任务，支持查看日志与产物。")

log_root = Path(st.session_state.get("log_root", "./log"))
_, factors = scan_logs(log_root)

status_filter = st.multiselect("状态", ["success", "failed", "running"], default=["success", "failed", "running"])
keyword = st.text_input("搜索 (ID/名称)", placeholder="输入关键词过滤")
filtered = [f for f in factors if f.status in status_filter]
if keyword:
    kw = keyword.lower()
    filtered = [f for f in filtered if kw in f.id.lower() or kw in f.name.lower()]

if filtered:
    data = format_records(filtered)
    st.dataframe(data, use_container_width=True, hide_index=True, column_config={"log_dir": "日志目录"})
else:
    st.info("暂无因子记录，先在工作台运行因子任务。")

st.markdown("---")
st.subheader("因子详情")
ids = [f.id for f in filtered]
if ids:
    selected = st.selectbox("选择因子任务", ids, index=0)
else:
    selected = None

if selected:
    record = next(f for f in filtered if f.id == selected)
    c1, c2, c3 = st.columns(3)
    c1.metric("状态", record.status)
    c2.metric("创建时间", record.created_at)
    c3.metric("Owner", record.owner or "-")
    c4, c5 = st.columns(2)
    c4.metric("产物数", len(record.artifacts or []))
    c5.metric("日志目录", record.log_dir.name)

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

    st.markdown("**可下载因子文件（自动定位）**")
    download_candidates = []
    for fp in (record.download_files or []):
        p = Path(fp)
        if p.exists() and p.is_file():
            download_candidates.append(p)
    if download_candidates:
        st.caption("以下文件来自工作区产物目录（按时间邻近匹配）：")
        for idx, fp in enumerate(download_candidates[:8], 1):
            with st.expander(f"文件 {idx}: {fp.name}", expanded=False):
                st.code(str(fp), language="text")
                try:
                    data = fp.read_bytes()
                    st.download_button(
                        label=f"⬇️ 下载 {fp.name}",
                        data=data,
                        file_name=fp.name,
                        mime="application/octet-stream",
                        key=f"download_{record.id}_{idx}_{fp.name}",
                    )
                except Exception as e:
                    st.warning(f"读取失败：{e}")
    else:
        st.caption("未定位到可下载文件（可先在工作台回放确认 workspace）。")

    st.markdown("**操作**")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🧭 去工作台回放", use_container_width=True):
            st.session_state["pending_log_path"] = record.log_dir.relative_to(log_root) if log_root.exists() else record.log_dir
            st.switch_page("pages/legacy.py")
    with col_b:
        if st.button("📜 打开回放页", use_container_width=True):
            st.session_state["pending_log_path"] = record.log_dir.relative_to(log_root) if log_root.exists() else record.log_dir
            st.switch_page("pages/playback.py")
else:
    st.caption("请选择一个因子记录查看详情。")

st.divider()
if st.button("🔄 刷新", use_container_width=True):
    st.rerun()
