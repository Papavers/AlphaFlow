import streamlit as st


def apply_shared_page_style() -> None:
    st.markdown(
        """
        <style>
            .stApp {
                background: linear-gradient(180deg, #f7f9fc 0%, #f3f6fb 100%);
            }
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            .stDeployButton {display: none;}
            [data-testid="stDecoration"] {display: none;}
            [data-testid="stHeader"] {
                background: transparent;
            }
            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
                border-right: 1px solid rgba(148, 163, 184, 0.14);
            }
            [data-testid="stSidebarNav"] {
                padding-top: 0.4rem;
            }
            [data-testid="stSidebarCollapsedControl"],
            button[kind="header"][aria-label*="sidebar" i],
            button[kind="header"][title*="sidebar" i] {
                display: flex !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
            [data-testid="stVerticalBlockBorderWrapper"] {
                background: rgba(255, 255, 255, 0.90);
                border: 1px solid rgba(148, 163, 184, 0.18);
                border-radius: 18px;
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
                transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
            }
            [data-testid="stVerticalBlockBorderWrapper"]:hover {
                transform: translateY(-1px);
                box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
                border-color: rgba(100, 116, 139, 0.26);
            }
            [data-testid="stMetric"] {
                background: rgba(255, 255, 255, 0.98);
                border: 1px solid rgba(148, 163, 184, 0.16);
                border-radius: 16px;
                padding: 12px 14px;
                box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
            }
            [data-testid="stForm"] {
                background: rgba(255, 255, 255, 0.98);
                border: 1px solid rgba(148, 163, 184, 0.16);
                border-radius: 18px;
                padding: 10px 10px 2px 10px;
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
            }
            [data-testid="stTextInputRootElement"],
            [data-testid="stTextAreaRootElement"],
            [data-baseweb="select"],
            [data-testid="stNumberInputContainer"] {
                border-radius: 14px;
            }
            .stButton > button, .stDownloadButton > button, .stLinkButton > a {
                border-radius: 12px !important;
                border: 1px solid rgba(148, 163, 184, 0.22) !important;
            }
            .csi-hero {
                padding: 20px 2px 10px 2px;
                margin-bottom: 12px;
                animation: csi-fade-up 320ms ease-out;
            }
            .csi-hero h1, .csi-hero h2, .csi-hero h3, .csi-hero p {
                color: #0f172a !important;
                margin: 0;
            }
            .csi-hero-subtitle {
                margin-top: 8px !important;
                color: #475569 !important;
                line-height: 1.6;
                font-size: 0.98rem;
            }
            .csi-chip-row {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 12px;
            }
            .csi-chip {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 5px 10px;
                border-radius: 999px;
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid rgba(148, 163, 184, 0.18);
                color: #334155;
                font-size: 0.86rem;
            }
            .csi-subtle-card {
                padding: 16px 18px;
                border-radius: 18px;
                background: rgba(255, 255, 255, 0.96);
                border: 1px solid rgba(148, 163, 184, 0.16);
                box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
            }
            .csi-section-title {
                display: flex;
                align-items: center;
                gap: 8px;
                font-weight: 700;
                font-size: 1.08rem;
                margin-bottom: 4px;
                color: #0f172a;
            }
            .csi-section-desc {
                color: #475569;
                font-size: 0.94rem;
                margin-bottom: 10px;
            }
            .csi-kicker {
                font-size: 0.78rem;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: #64748b;
                margin-bottom: 6px;
            }
            .csi-mini-link {
                font-size: 0.84rem;
                color: #64748b;
                text-decoration: none;
            }
            .csi-mini-link:hover {
                color: #0f172a;
                text-decoration: underline;
            }
            @keyframes csi-fade-up {
                from {
                    opacity: 0;
                    transform: translateY(8px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_hero(title: str, subtitle: str | None = None, chips: list[str] | None = None) -> None:
    chip_html = ""
    if chips:
        chip_html = '<div class="csi-chip-row">' + "".join(
            f'<span class="csi-chip">{chip}</span>' for chip in chips
        ) + "</div>"
    subtitle_html = f'<p class="csi-hero-subtitle">{subtitle}</p>' if subtitle else ""
    st.markdown(
        f"""
        <div class="csi-hero">
            <div class="csi-kicker">AlphaFlow</div>
            <h2>{title}</h2>
            {subtitle_html}
            {chip_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_intro(title: str, desc: str | None = None) -> None:
    desc_html = f'<div class="csi-section-desc">{desc}</div>' if desc else ""
    st.markdown(
        f"""
        <div class="csi-section-title">{title}</div>
        {desc_html}
        """,
        unsafe_allow_html=True,
    )


def render_mini_link(label: str, href: str) -> None:
    st.markdown(f'<a class="csi-mini-link" href="{href}">{label}</a>', unsafe_allow_html=True)

def render_app_sidebar(current_page: str) -> None:
    nav_items = [
        ("首页", "main.py", "🚀"),
        ("任务工作台", "pages/home.py", "🏠"),
        ("任务历史", "pages/tasks.py", "📑"),
        ("因子记录", "pages/factors.py", "🧬"),
        ("结果回放", "pages/playback.py", "🎞️"),
        ("用户管理", "pages/users.py", "👥"),
        ("设置", "pages/settings.py", "⚙️"),
    ]

    with st.sidebar:
        st.markdown("### AlphaFlow")
        st.divider()

        for label, page, icon in nav_items:
            st.page_link(page, label=label, icon=icon, disabled=(current_page == page))

        st.divider()
        st.page_link("pages/legacy.py", label="原版工作台", icon="↗")

        if st.button("退出登录", use_container_width=True):
            st.session_state.pop("auth_token", None)
            st.session_state.pop("user", None)
            st.switch_page("pages/login.py")