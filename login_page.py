import streamlit as st

from ui_helpers import inject_css_file


def render_login_page(*, verify_user, update_last_login):
    inject_css_file("assets/login_page.css")

    st.markdown('<div class="login-page">', unsafe_allow_html=True)
    st.markdown('<div class="login-content">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">变电站防误操作智能审核系统</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-sub">基于 LangChain 多智能体博弈的操作安全审核平台</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="login-logo">
            <svg viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg">
                <defs>
                    <linearGradient id="loginGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" style="stop-color:#9c94ff"/>
                        <stop offset="50%" style="stop-color:#6B66CC"/>
                        <stop offset="100%" style="stop-color:#483d99"/>
                    </linearGradient>
                    <filter id="glow">
                        <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
                        <feMerge>
                            <feMergeNode in="coloredBlur"/>
                            <feMergeNode in="SourceGraphic"/>
                        </feMerge>
                    </filter>
                </defs>
                <path fill="url(#loginGrad)" d="M50 6 L90 26 L90 56 Q90 84 50 108 Q10 84 10 56 L10 26 Z"/>
                <path fill="#FFD700" filter="url(#glow)" d="M52 22 L38 58 L48 58 L42 78 L62 48 L50 48 L58 22 Z">
                    <animate attributeName="opacity" values="0.7;1;0.7" dur="0.5s" repeatCount="indefinite"/>
                </path>
            </svg>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, form_col, _ = st.columns([1.2, 2.1, 1.2])
    with form_col:
        with st.form("login_form", clear_on_submit=False):
            login_user = st.text_input("用户名", placeholder="请输入用户名", label_visibility="collapsed")
            login_pwd = st.text_input("密码", placeholder="请输入密码", type="password", label_visibility="collapsed")
            submitted = st.form_submit_button("登 录", type="primary", use_container_width=True)

            if submitted:
                if login_user.strip() and login_pwd:
                    user = verify_user(login_user.strip(), login_pwd)
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.logged_in_user = user["username"]
                        st.session_state.user_role = user["role"]
                        st.session_state.display_name = user.get("display_name", user["username"])
                        update_last_login(user["username"])
                        st.rerun()
                    else:
                        st.error("用户名或密码错误")
                else:
                    st.warning("请输入用户名和密码")

        st.markdown(
            """
            <div class="login-demo">
                <strong>默认账号：</strong>admin / admin（管理员）&nbsp;&nbsp;operator / operator（操作员）
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div></div>", unsafe_allow_html=True)
    st.stop()
