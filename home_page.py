import streamlit as st


SHIELD_ICON_HTML = """
<span class="shield-logo shield-logo--sm">
    <svg class="shield-svg" viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg">
        <defs>
            <linearGradient id="shieldGradMd" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#9c94ff"/>
                <stop offset="50%" style="stop-color:#6B66CC"/>
                <stop offset="100%" style="stop-color:#483d99"/>
            </linearGradient>
        </defs>
        <path fill="url(#shieldGradMd)" d="M50 6 L90 26 L90 56 Q90 84 50 108 Q10 84 10 56 L10 26 Z"/>
        <path class="bolt-path" fill="#FFD700" d="M52 22 L38 58 L48 58 L42 78 L62 48 L50 48 L58 22 Z">
            <animate attributeName="opacity" values="0.8;1;0.8" dur="0.7s" repeatCount="indefinite"/>
        </path>
    </svg>
</span>
"""


def _render_home_card(*, icon_html: str, title: str, desc: str):
    st.markdown(
        f"""
        <div class="module-card-home-wrap">
            <div class="module-icon">{icon_html}</div>
            <div class="module-title">{title}</div>
            <div class="module-desc">{desc}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_home_entry(*, icon_html: str, title: str, desc: str, button_label: str, page_key: str, button_key: str):
    _render_home_card(icon_html=icon_html, title=title, desc=desc)
    if st.button(button_label, use_container_width=True, type="primary", key=button_key):
        st.session_state.current_page = page_key
        st.rerun()


def render_home_page():
    st.markdown(
        """
        <div class="main-title-container">
            <div class="main-title">⚡ 智电卫士 | 变电站防误操作智能审核系统</div>
            <div class="main-subtitle">基于 LangChain 多智能体博弈的操作安全审核平台</div>
            <div class="main-badge">🛡️ 多智能体协同 | ⚠️ 五防规则校验 | 📚 RAG 知识库</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<p class="core-modules-heading">🔧 核心功能</p>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        _render_home_entry(
            icon_html=SHIELD_ICON_HTML,
            title="操作审核",
            desc="多智能体协同分析 / 操作风险智能评估",
            button_label="🛡️ 进入操作审核",
            page_key="操作审核",
            button_key="home_to_operation_audit",
        )
    with col2:
        _render_home_entry(
            icon_html="📋",
            title="审核历史",
            desc="历史审核记录 / 统计分析报表",
            button_label="📋 进入审核历史",
            page_key="审核历史",
            button_key="home_to_audit_history",
        )

    col3, col4 = st.columns(2)
    with col3:
        _render_home_entry(
            icon_html="🔔",
            title="告警中心",
            desc="告警处理 / 通知设置",
            button_label="🔔 进入告警中心",
            page_key="告警中心",
            button_key="home_to_alarm",
        )
    with col4:
        _render_home_entry(
            icon_html="📈",
            title="统计分析",
            desc="多维度数据统计 / 趋势分析",
            button_label="📈 进入统计分析",
            page_key="统计分析",
            button_key="home_to_stats",
        )

    col5, col6, col7 = st.columns(3)
    with col5:
        _render_home_entry(
            icon_html="⚙️",
            title="系统配置",
            desc="API 配置 / 电站信息设置",
            button_label="⚙️ 进入系统配置",
            page_key="系统配置",
            button_key="home_to_system_config",
        )
    with col6:
        _render_home_entry(
            icon_html="📝",
            title="操作票管理",
            desc="大模型生成 / 标准操作票库",
            button_label="📝 进入操作票管理",
            page_key="操作票管理",
            button_key="home_to_ticket",
        )
    with col7:
        _render_home_entry(
            icon_html="💬",
            title="规程问答",
            desc="RAG 智能问答 / 规程检索",
            button_label="💬 进入规程问答",
            page_key="规程问答",
            button_key="home_to_qa",
        )

    col8, col9 = st.columns(2)
    with col8:
        _render_home_entry(
            icon_html="📚",
            title="知识库管理",
            desc="规程录入 / 分类管理",
            button_label="📚 进入知识库管理",
            page_key="知识库管理",
            button_key="home_to_kb",
        )
    if st.session_state.get("user_role") == "管理员":
        with col9:
            _render_home_entry(
                icon_html="👥",
                title="用户管理",
                desc="用户管理 / 权限设置",
                button_label="👥 进入用户管理",
                page_key="用户管理",
                button_key="home_to_user_management",
            )
