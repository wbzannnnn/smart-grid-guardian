from datetime import datetime

import pandas as pd
import streamlit as st

from ui_helpers import render_page_title


def render_alarm_page(
    *,
    get_alarm_stats,
    get_alarms,
    update_alarm_status,
    save_alarm,
    get_app_db,
):
    render_page_title("assets/alarm_page.css", "alarm-title", "🔔 告警中心")

    try:
        alarm_stats = get_alarm_stats()
    except Exception:
        alarm_stats = {
            "total": 0,
            "pending": 0,
            "processing": 0,
            "resolved": 0,
            "today": 0,
            "critical": 0,
            "warning": 0,
            "info": 0,
        }

    col_a1, col_a2, col_a3, col_a4, col_a5 = st.columns(5)
    with col_a1:
        st.metric("今日告警", alarm_stats.get("today", 0))
    with col_a2:
        st.metric("待处理", alarm_stats.get("pending", 0), delta=None, delta_color="off")
    with col_a3:
        st.metric("处理中", alarm_stats.get("processing", 0), delta=None, delta_color="off")
    with col_a4:
        st.metric("已处理", alarm_stats.get("resolved", 0), delta=None, delta_color="normal")
    with col_a5:
        st.metric("总计", alarm_stats.get("total", 0))

    col_level1, col_level2, col_level3 = st.columns(3)
    with col_level1:
        st.metric("🔴 严重告警", alarm_stats.get("critical", 0), delta=None, delta_color="off")
    with col_level2:
        st.metric("🟡 中危告警", alarm_stats.get("warning", 0), delta=None, delta_color="off")
    with col_level3:
        st.metric("🔵 低危告警", alarm_stats.get("info", 0), delta=None, delta_color="off")

    st.divider()

    def _render_alarm_card(alarm, key_prefix: str = "alarm"):
        level = alarm.get("level", "info")
        status = alarm.get("status", "待处理")
        level_colors = {"critical": "#fee2e2", "warning": "#fef3c7", "info": "#dbeafe"}
        level_text_colors = {"critical": "#991b1b", "warning": "#92400e", "info": "#1e40af"}
        level_badge_colors = {"critical": "#ef4444", "warning": "#f59e0b", "info": "#3b82f6"}
        level_labels = {"critical": "严重", "warning": "中危", "info": "低危"}
        status_colors = {"待处理": "#fef3c7", "处理中": "#dbeafe", "已处理": "#d1fae5", "已忽略": "#f1f5f9"}
        status_text_colors = {"待处理": "#92400e", "处理中": "#1e40af", "已处理": "#065f46", "已忽略": "#64748b"}

        level_bg = level_colors.get(level, "#f1f5f9")
        level_txt = level_text_colors.get(level, "#333")
        badge_bg = level_badge_colors.get(level, "#888")
        status_bg = status_colors.get(status, "#f1f5f9")
        status_txt = status_text_colors.get(status, "#333")
        level_label = level_labels.get(level, "未知")

        created = alarm.get("created_at", "")
        if created:
            try:
                dt = datetime.fromisoformat(created)
                created = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        st.markdown(
            f"""
            <div style="background:{level_bg};border-radius:12px;padding:16px;margin:8px 0;border-left:4px solid {badge_bg};">
                <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px;">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="background:{badge_bg};color:white;padding:3px 12px;border-radius:20px;font-size:0.8rem;font-weight:600;">{level_label}</span>
                        <span style="background:{status_bg};color:{status_txt};padding:3px 12px;border-radius:20px;font-size:0.8rem;font-weight:600;">{status}</span>
                        <span style="font-weight:700;color:{level_txt};font-size:1rem;">{alarm.get('title', '')}</span>
                    </div>
                    <div style="color:#888;font-size:0.8rem;">{created}</div>
                </div>
                <div style="color:#555;font-size:0.9rem;line-height:1.6;margin-bottom:8px;">{alarm.get('content', '')}</div>
                <div style="display:flex;gap:16px;color:#666;font-size:0.8rem;">
                    <span>📁 {alarm.get('alarm_type', '')}</span>
                    <span>📍 {alarm.get('source', '')}</span>
                    <span>👤 {alarm.get('operator', '')}</span>
                    <span>🔖 {alarm.get('alarm_id', '')}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_act1, col_act2, col_act3 = st.columns([1, 1, 1])
        with col_act1:
            if status == "待处理" and st.button("▶️ 开始处理", key=f"{key_prefix}_start_{alarm.get('alarm_id')}", use_container_width=True):
                update_alarm_status(alarm.get("alarm_id", ""), "处理中", handler=st.session_state.get("logged_in_user", ""))
                st.rerun()
        with col_act2:
            if status in ("待处理", "处理中") and st.button("✅ 处理完成", key=f"{key_prefix}_resolve_{alarm.get('alarm_id')}", use_container_width=True):
                update_alarm_status(alarm.get("alarm_id", ""), "已处理", handler=st.session_state.get("logged_in_user", ""), handle_result="已处理")
                st.rerun()
        with col_act3:
            if status == "待处理" and st.button("⏭️ 忽略", key=f"{key_prefix}_ignore_{alarm.get('alarm_id')}", use_container_width=True):
                update_alarm_status(alarm.get("alarm_id", ""), "已忽略", handler=st.session_state.get("logged_in_user", ""), handle_result="已忽略")
                st.rerun()
        st.markdown("---")

    tab_all, tab_pending, tab_processing, tab_resolved = st.tabs(["全部告警", "待处理", "处理中", "已处理"])
    filter_level = st.selectbox("告警级别", ["全部", "critical", "warning", "info"], format_func=lambda x: {"全部": "全部级别", "critical": "严重", "warning": "中危", "info": "低危"}.get(x, x))

    with tab_all:
        alarms = get_alarms(limit=200, level=filter_level if filter_level != "全部" else None)
        if not alarms:
            st.info("暂无告警记录")
        else:
            st.success(f"共 {len(alarms)} 条告警")
            for alarm in alarms:
                _render_alarm_card(alarm, key_prefix="all")

    with tab_pending:
        alarms_p = [a for a in get_alarms(limit=200, status="待处理", level=filter_level if filter_level != "全部" else None)]
        if not alarms_p:
            st.info("暂无待处理告警")
        else:
            st.success(f"共 {len(alarms_p)} 条待处理告警")
            for alarm in alarms_p:
                _render_alarm_card(alarm, key_prefix="pending")

    with tab_processing:
        alarms_pr = [a for a in get_alarms(limit=200, status="处理中", level=filter_level if filter_level != "全部" else None)]
        if not alarms_pr:
            st.info("暂无处理中告警")
        else:
            st.success(f"共 {len(alarms_pr)} 条处理中告警")
            for alarm in alarms_pr:
                _render_alarm_card(alarm, key_prefix="processing")

    with tab_resolved:
        alarms_r = [a for a in get_alarms(limit=200, status="已处理", level=filter_level if filter_level != "全部" else None)]
        if not alarms_r:
            st.info("暂无已处理告警")
        else:
            st.success(f"共 {len(alarms_r)} 条已处理告警")
            for alarm in alarms_r:
                _render_alarm_card(alarm, key_prefix="resolved")

    st.divider()

    with st.expander("🔧 告警管理", expanded=False):
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.subheader("创建测试告警")
            test_type = st.selectbox("告警类型", ["高危操作告警", "中危操作告警", "设备异常告警", "系统告警"])
            test_level = st.selectbox("告警级别", ["critical", "warning", "info"], format_func=lambda x: {"critical": "严重", "warning": "中危", "info": "低危"}.get(x, x))
            test_title = st.text_input("告警标题", placeholder="请输入告警标题")
            test_content = st.text_area("告警内容", placeholder="请输入告警详情")
            if st.button("📢 提交告警", type="primary"):
                if test_title:
                    alarm_data = {
                        "alarm_id": f"AL{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "alarm_type": test_type,
                        "level": test_level,
                        "title": test_title,
                        "content": test_content or test_title,
                        "source": "手动创建",
                        "status": "待处理",
                        "operator": st.session_state.get("logged_in_user", "未知"),
                        "created_at": datetime.now().isoformat(),
                    }
                    save_alarm(alarm_data)
                    st.success("告警创建成功！")
                    st.rerun()
                else:
                    st.warning("请填写告警标题")
        with col_c2:
            st.subheader("告警数据概览")
            try:
                all_alarms = get_alarms(limit=1000)
                if all_alarms:
                    df = pd.DataFrame(all_alarms)
                    st.dataframe(df[["alarm_id", "title", "level", "status", "created_at"]], use_container_width=True, hide_index=True)
                else:
                    st.info("暂无告警数据")
            except Exception as e:
                st.warning(f"数据加载失败：{e}")

    with st.expander("⚠️ 数据清理", expanded=False):
        st.warning("以下操作不可逆，请谨慎使用！")
        col_cl1, col_cl2 = st.columns(2)
        with col_cl1:
            if st.button("🗑️ 清空所有告警", type="secondary"):
                conn = get_app_db()
                try:
                    conn.execute("DELETE FROM alarms")
                    conn.commit()
                    st.success("所有告警已清空！")
                    st.rerun()
                finally:
                    conn.close()
        with col_cl2:
            if st.button("🗑️ 清空调试告警", type="secondary"):
                conn = get_app_db()
                try:
                    conn.execute("DELETE FROM alarms WHERE source = '手动创建'")
                    conn.commit()
                    st.success("手动创建的告警已清空！")
                    st.rerun()
                finally:
                    conn.close()
