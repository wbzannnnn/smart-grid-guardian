import streamlit as st


def render_system_config_page(default_api_key: str) -> None:
    st.subheader("⚙️ 系统配置")
    st.subheader("API 配置")
    api_key_input = st.text_input(
        "DeepSeek API Key",
        type="password",
        value=st.session_state.get("api_key") or default_api_key or "",
    )

    st.divider()
    st.subheader("电站信息")
    col1, col2 = st.columns(2)
    with col1:
        station_name = st.text_input(
            "电站名称",
            value=st.session_state.get("station_name") or "一号电站",
            placeholder="如：一号电站",
        )
        station_code = st.text_input(
            "电站编码",
            value=st.session_state.get("station_code") or "",
            placeholder="XX220",
        )
    with col2:
        username = st.text_input(
            "用户名",
            value=st.session_state.get("username") or "",
            placeholder="请输入姓名",
        )
        employee_id = st.text_input(
            "工号",
            value=st.session_state.get("employee_id") or "",
            placeholder="请输入工号",
        )

    st.divider()
    if st.button("💾 保存配置", type="primary", use_container_width=True):
        if station_name and station_code:
            st.session_state.station_name = station_name
            st.session_state.station_code = station_code
            st.session_state.username = username
            st.session_state.employee_id = employee_id
            st.session_state.data_source_configured = True
            if api_key_input and len(api_key_input) > 10:
                st.session_state.api_key = api_key_input
            st.success("✅ 配置已保存！")
            st.rerun()
        else:
            st.error("❌ 请填写电站名称和编码")
