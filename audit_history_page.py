import html

import streamlit as st

from ui_helpers import render_page_title


def render_audit_history_page(*, get_audit_records, risk_label_and_color):
    render_page_title("assets/history_page.css", "history-title", "📋 审核历史记录")

    try:
        db_history = get_audit_records(limit=200)
    except Exception:
        db_history = []

    mem_history = st.session_state.get("audit_history", [])
    all_history = db_history.copy()
    existing_ids = {r.get("record_id") for r in db_history}
    for r in mem_history:
        if r.get("record_id") and r.get("record_id") not in existing_ids:
            all_history.insert(0, r)

    if not all_history:
        st.info("📭 暂无审核历史记录，请先在「操作审核」中提交审核。")
        if st.button("⬅️ 返回操作审核"):
            st.session_state.current_page = "操作审核"
            st.rerun()
        return

    col_filter1, col_filter2 = st.columns([1, 3])
    with col_filter1:
        filter_result = st.selectbox("筛选结果", ["全部", "ALLOW", "DENY"], key="hist_filter")
    with col_filter2:
        search_cmd = st.text_input("🔍 搜索操作指令", placeholder="输入指令关键词...", key="hist_search")

    filtered = all_history
    if filter_result != "全部":
        filtered = [r for r in filtered if r.get("result") == filter_result or r.get("decision") == filter_result]
    if search_cmd:
        filtered = [r for r in filtered if search_cmd.lower() in r.get("command", "").lower()]

    st.success(f"共 {len(filtered)} 条记录（总计 {len(all_history)} 条）")

    allow_cnt = sum(1 for r in all_history if r.get("result") == "ALLOW" or r.get("decision") == "ALLOW")
    deny_cnt = sum(1 for r in all_history if r.get("result") == "DENY" or r.get("decision") == "DENY")

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        st.metric("总审核数", len(all_history))
    with col_s2:
        st.metric("✅ 通过", allow_cnt)
    with col_s3:
        st.metric("❌ 拒绝", deny_cnt)

    st.divider()

    def fmt_html(text: str) -> str:
        return html.escape(str(text or "（暂无）")).replace("\n", "<br/>")

    for record in reversed(filtered):
        result = record.get("result") or record.get("decision", "DENY")
        result_icon = "✅" if result == "ALLOW" else "❌"
        risk = record.get("risk_level", "MEDIUM")
        r_cn, r_col = risk_label_and_color(risk)
        command_text = html.escape(record.get("command", ""))
        display_time = record.get("created_at", "") or record.get("timestamp", "")

        with st.container():
            st.markdown(
                f"""
                <div style="background:white;border-radius:12px;padding:16px;margin:10px 0;box-shadow:0 2px 8px rgba(0,0,0,0.07);border-left:4px solid {r_col};">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:8px;">
                        <div style="display:flex;align-items:flex-start;gap:12px;flex:1;min-width:0;">
                            <span style="font-size:1.5rem;">{result_icon}</span>
                            <div style="font-weight:700;color:#333;font-size:1.05rem;line-height:1.55;white-space:normal;word-break:break-word;overflow-wrap:anywhere;flex:1;">{command_text}</div>
                        </div>
                        <div style="display:flex;align-items:center;gap:10px;flex-shrink:0;">
                            <span style="background:{r_col};color:white;padding:3px 12px;border-radius:20px;font-size:0.8rem;font-weight:600;">{r_cn}</span>
                            <span style="color:#888;font-size:0.85rem;">{display_time[:19]}</span>
                        </div>
                    </div>
                    <div style="display:flex;gap:20px;color:#666;font-size:0.85rem;margin-top:4px;flex-wrap:wrap;">
                        <span>🎫 {record.get('ticket_no', '')}</span>
                        <span>📋 {record.get('task_type', '')}</span>
                        <span>👤 {record.get('operator', '')}</span>
                        <span>📊 置信度 {record.get('confidence', 80)}%</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            with st.expander(f"查看完整详情 · {record.get('record_id', '') or record.get('ticket_no', '')}", expanded=False):
                col_l, col_r = st.columns(2)
                with col_l:
                    st.markdown(
                        f"""
                        <div style="background:#fafafa;border:1px solid #ececf2;border-radius:12px;padding:16px;height:100%;">
                            <div style="font-weight:800;color:#333;margin-bottom:10px;">📋 基本信息</div>
                            <div style="color:#555;line-height:1.8;">
                                <strong>审核结果：</strong>{html.escape(result)}<br/>
                                <strong>风险等级：</strong>{html.escape(r_cn)}<br/>
                                <strong>置信度：</strong>{html.escape(str(record.get('confidence', 80)))}%<br/>
                                <strong>任务类型：</strong>{html.escape(record.get('task_type', '') or '（暂无）')}<br/>
                                <strong>操作票号：</strong>{html.escape(record.get('ticket_no', '') or '（暂无）')}<br/>
                                <strong>操作员：</strong>{html.escape(record.get('operator', '') or '（暂无）')}<br/>
                                <strong>时间：</strong>{html.escape(display_time[:19] or '（暂无）')}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_r:
                    st.markdown(
                        f"""
                        <div style="background:#fafafa;border:1px solid #ececf2;border-radius:12px;padding:16px;height:100%;">
                            <div style="font-weight:800;color:#333;margin-bottom:10px;">📝 操作指令</div>
                            <div style="color:#333;line-height:1.8;">{fmt_html(record.get('command', ''))}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                st.markdown("#### 🤖 多智能体完整返回")
                agent_cards = [
                    ("👮 审核员意见", record.get("auditor_text", ""), "#e8f5e9", "#2e7d32"),
                    ("🥷 红队攻击分析", record.get("red_text", ""), "#ffebee", "#c62828"),
                    ("🛡️ 蓝队防御分析", record.get("blue_text", ""), "#e3f2fd", "#1565c0"),
                    ("📚 规程专家意见", record.get("expert_text", ""), "#fff8e1", "#e65100"),
                ]
                col_a, col_b = st.columns(2)
                for idx, (title, text, bg, border) in enumerate(agent_cards):
                    target = col_a if idx % 2 == 0 else col_b
                    with target:
                        st.markdown(
                            f"""
                            <div style="background:{bg};border-left:4px solid {border};border-radius:12px;padding:16px;margin:8px 0;min-height:140px;">
                                <div style="font-weight:800;color:#333;margin-bottom:10px;">{title}</div>
                                <div style="color:#333;line-height:1.75;font-size:0.95rem;">{fmt_html(text)}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                st.markdown("#### ⚖️ 最终决策原文")
                st.markdown(
                    f"""
                    <div style="background:#f8fafc;border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin:8px 0;">
                        <div style="font-weight:800;color:#333;margin-bottom:10px;">最终决策</div>
                        <div style="color:#334155;line-height:1.8;">{fmt_html(record.get('decision_text', ''))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown("#### 📌 结论摘要")
                col_v, col_m = st.columns(2)
                with col_v:
                    st.markdown(
                        f"""
                        <div style="background:#fafafa;border:1px solid #ececf2;border-radius:12px;padding:16px;height:100%;">
                            <div style="font-weight:800;color:#333;margin-bottom:10px;">⚠️ 违反规则</div>
                            <div style="color:#c62828;line-height:1.75;">{fmt_html(record.get('violations', '无'))}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_m:
                    st.markdown(
                        f"""
                        <div style="background:#fafafa;border:1px solid #ececf2;border-radius:12px;padding:16px;height:100%;">
                            <div style="font-weight:800;color:#333;margin-bottom:10px;">💡 建议措施</div>
                            <div style="color:#1e3a8a;line-height:1.75;">{fmt_html(record.get('measures', '无'))}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

    if st.button("⬅️ 返回操作审核"):
        st.session_state.current_page = "操作审核"
        st.rerun()
