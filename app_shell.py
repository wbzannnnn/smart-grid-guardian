import streamlit as st


PAGE_TITLE_MAP = {
    "home": "首页",
    "操作审核": "操作审核",
    "操作票管理": "操作票管理",
    "告警中心": "告警中心",
    "统计分析": "统计分析",
    "系统配置": "系统配置",
    "知识库管理": "知识库管理",
    "规程问答": "规程问答",
    "用户管理": "用户管理",
    "审核历史": "审核历史",
}


def _sidebar_nav_btn(label: str, page_key: str):
    is_active = st.session_state.current_page == page_key
    btn_type = "primary" if is_active else "secondary"
    if st.button(label, type=btn_type, use_container_width=True, key=f"nav_{page_key}"):
        st.session_state.current_page = page_key
        st.rerun()


def render_app_header():
    current_page = st.session_state.current_page
    current_title = PAGE_TITLE_MAP.get(current_page, current_page)
    user = st.session_state.get("logged_in_user", "admin")
    display_name = st.session_state.get("display_name", "系统管理员")
    role = st.session_state.get("user_role", "管理员")

    st.markdown(
        f"""
        <div class="app-header-wrap">
            <div class="app-header-brand">
                <div class="shield-logo shield-logo--header" aria-hidden="true">
                    <svg class="shield-svg" viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                            <linearGradient id="shieldGradHdr" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" style="stop-color:#9c94ff"/>
                                <stop offset="50%" style="stop-color:#6B66CC"/>
                                <stop offset="100%" style="stop-color:#483d99"/>
                            </linearGradient>
                        </defs>
                        <path fill="url(#shieldGradHdr)" d="M50 6 L90 26 L90 56 Q90 84 50 108 Q10 84 10 56 L10 26 Z"/>
                        <path class="bolt-path" fill="#FFD700" d="M52 22 L38 58 L48 58 L42 78 L62 48 L50 48 L58 22 Z">
                            <animate attributeName="opacity" values="0.8;1;0.8" dur="0.7s" repeatCount="indefinite"/>
                        </path>
                    </svg>
                </div>
                <div class="app-header-text-block">
                    <div class="app-header-title">智电卫士 | 变电站防误操作智能审核系统</div>
                    <div class="app-header-sub">基于 LangChain 多智能体博弈的操作安全审核平台</div>
                    <div class="app-header-user">👁 当前用户: {display_name}（{user}） · 角色: <span class="status-pill pill-blue">{role}</span></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, right_col = st.columns([5, 1])
    with right_col:
        if st.button("退出登录", key="header_logout"):
            st.session_state.authenticated = False
            st.session_state.current_page = "home"
            st.session_state.last_audit_full = None
            st.rerun()

    st.markdown(
        '<hr style="margin:12px 0 16px;border:none;border-top:1px solid #e8e8e8;"/>',
        unsafe_allow_html=True,
    )

    left_col, right_col = st.columns([4, 1])
    with left_col:
        st.markdown(
            f'<p class="breadcrumb-text">📍 当前位置: <b>{current_title}</b></p>',
            unsafe_allow_html=True,
        )
    with right_col:
        if st.button("🏠 返回首页", key="breadcrumb_home"):
            st.session_state.current_page = "home"
            st.rerun()


def render_sidebar(*, effective_api_key: str, app_version: str, last_update: str):
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-header">
                <div class="sidebar-title">智电卫士</div>
                <div class="sidebar-subtitle">变电站防误操作智能审核系统</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.current_page == "home":
            if st.button("🏠 返回首页", use_container_width=True, key="sidebar_home"):
                st.session_state.current_page = "home"
                st.rerun()
            st.divider()

        st.markdown('<p class="nav-section-title">功能</p>', unsafe_allow_html=True)
        _sidebar_nav_btn("操作审核", "操作审核")
        _sidebar_nav_btn("审核历史", "审核历史")
        _sidebar_nav_btn("操作票管理", "操作票管理")
        _sidebar_nav_btn("规程问答", "规程问答")

        st.markdown('<p class="nav-section-title">数据</p>', unsafe_allow_html=True)
        _sidebar_nav_btn("告警中心", "告警中心")
        _sidebar_nav_btn("统计分析", "统计分析")
        _sidebar_nav_btn("知识库管理", "知识库管理")

        st.markdown('<p class="nav-section-title">系统</p>', unsafe_allow_html=True)
        _sidebar_nav_btn("系统配置", "系统配置")
        if st.session_state.get("user_role") == "管理员":
            _sidebar_nav_btn("用户管理", "用户管理")

        st.divider()
        st.subheader("系统状态")
        api_ok = bool(effective_api_key) and len(str(effective_api_key)) > 10
        st.markdown(
            f'<span class="status-pill pill-{"green" if api_ok else "gray"}">{"API 已配置" if api_ok else "API 未配置"}</span>',
            unsafe_allow_html=True,
        )

        station = st.session_state.get("station_name", "") or "未配置"
        if station != "未配置":
            st.markdown(
                f'<span class="status-pill pill-blue">{station}</span>',
                unsafe_allow_html=True,
            )

        cfg_ok = st.session_state.get("data_source_configured", False)
        st.markdown(
            f'<span class="status-pill pill-{"green" if cfg_ok else "gray"}">{"电站已配置" if cfg_ok else "电站未配置"}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="sidebar-footer">框架: LangChain + Streamlit<br/>版本: {app_version}<br/>最后更新: {last_update}</div>',
            unsafe_allow_html=True,
        )
