import html
from datetime import datetime
import traceback

import streamlit as st

from ui_helpers import inject_css_file, render_page_title


def render_operation_audit_page(
    *,
    get_kb,
    agent_debate_system_cls,
    api_key: str,
    api_base_url: str,
    save_audit_record,
    generate_alarm_from_audit,
    generate_audit_report_pdf,
    risk_label_and_color,
):
    if not api_key or len(str(api_key)) <= 10:
        st.error("⚠️ 请先在「系统配置」中配置 DeepSeek API Key")
        st.page_link("app.py", page="系统配置", label="前往系统配置")
        st.stop()

    render_page_title("assets/audit_page.css", "section-title", "⚡ 操作指令审核")

    task_type = st.selectbox(
        "📋 操作任务类型",
        ["线路停送电", "主变停送电", "母线倒闸", "电容器投切", "其他操作"],
        key="audit_task_type",
    )
    user_command = st.text_area(
        "📝 具体操作指令",
        placeholder="请使用标准调度术语输入，如：10kV 101 线路由运行转检修",
        height=100,
        key="audit_command_text",
    )
    st.markdown(
        """
        <div class="spec-box">
            <strong>📌 操作指令规范：</strong><br/>
            • 使用标准调度术语 &nbsp;&nbsp;• 明确设备名称和编号<br/>
            • 明确操作任务和目标状态 &nbsp;&nbsp;• 遵循操作票填写规范
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_btn, col_hist_link = st.columns([2, 1])
    with col_btn:
        if st.button("🚀 开始智能审核", type="primary", use_container_width=True, key="btn_run_audit"):
            if user_command and user_command.strip():
                try:
                    with st.spinner("🧠 多智能体协同博弈审核中，请稍候..."):
                        kb = get_kb()
                        rag_results = kb.search(user_command.strip(), top_k=2, use_llm_embed=False)
                        rag_context = "\n\n".join([
                            f"【{d['category']}】{d['title']}：{str(d['content']).replace(chr(10), ' ')[:140]}"
                            for d in rag_results
                        ]) if rag_results else "（未检索到相关规程）"

                        debate_system = agent_debate_system_cls(
                            api_key=api_key,
                            base_url=api_base_url,
                            rag_kb=kb,
                        )
                        audit_id = f"AUDIT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                        ctx = {"context": rag_context, "task_type": task_type, "audit_id": audit_id}
                        results = debate_system.run_debate(user_command.strip(), ctx)
                        results["rag_results"] = rag_results
                        results["rag_context"] = rag_context

                        record_id = f"A{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        audit_record = {
                            "record_id": record_id,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "created_at": datetime.now().isoformat(),
                            "command": user_command.strip(),
                            "result": results["decision_parsed"]["decision"],
                            "decision": results["decision_parsed"]["decision"],
                            "risk_level": results["decision_parsed"]["risk_level"],
                            "confidence": results["decision_parsed"]["confidence"],
                            "operator": st.session_state.get("username") or st.session_state.get("logged_in_user", "未知"),
                            "ticket_no": f"T{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            "task_type": task_type,
                            "violations": results["decision_parsed"].get("violations", ""),
                            "measures": results["decision_parsed"].get("measures", ""),
                            "auditor_text": results.get("auditor", ""),
                            "red_text": results.get("red", ""),
                            "blue_text": results.get("blue", ""),
                            "expert_text": results.get("expert", ""),
                            "decision_text": results.get("decision", ""),
                            "rag_context": rag_context,
                            "station_name": st.session_state.get("station_name", ""),
                        }
                        try:
                            save_audit_record(audit_record)
                        except Exception:
                            pass
                        try:
                            risk = results["decision_parsed"].get("risk_level", "LOW")
                            if risk in ("HIGH", "MEDIUM"):
                                generate_alarm_from_audit(audit_record, risk)
                        except Exception:
                            pass

                        st.session_state.audit_history.append(audit_record)
                        st.session_state.last_audit_full = {
                            "results": results,
                            "task_type": task_type,
                            "user_command": user_command.strip(),
                            "ticket_no": audit_record["ticket_no"],
                            "timestamp": audit_record["timestamp"],
                            "dp": results["decision_parsed"],
                            "record_id": record_id,
                        }
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ 审核失败：{str(e)}")
                    st.code(traceback.format_exc())
            else:
                st.warning("⚠️ 请输入操作指令")

    with col_hist_link:
        if st.button("📋 审核历史", use_container_width=True):
            st.session_state.current_page = "审核历史"
            st.rerun()

    if st.session_state.last_audit_full:
        inject_css_file("assets/audit_report.css")
        la = st.session_state.last_audit_full
        results = la["results"]
        dp = la.get("dp", results.get("decision_parsed", {}))
        decision = dp.get("decision", "DENY")
        risk = dp.get("risk_level", "MEDIUM")
        r_cn, r_col = risk_label_and_color(risk)

        def fmt_text(t):
            if not t:
                return "（暂无）"
            return t.strip()

        def fmt_html(t):
            text = fmt_text(t)
            return html.escape(text).replace("\n", "<br/>")

        st.divider()
        st.markdown("---")
        st.markdown("### 📄 审核报告单")

        col_top_l, col_top_r = st.columns([1, 1])
        with col_top_l:
            dec_cn = "🔴 拒绝执行" if decision == "DENY" else "🟢 允许执行"
            dec_color = "#ef4444" if decision == "DENY" else "#10b981"
            st.markdown(
                f"""
                <div style="text-align:center;padding:20px;background:white;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
                    <div style="font-size:2rem;font-weight:800;color:{dec_color};">{dec_cn}</div>
                    <div style="margin-top:12px;font-size:1.2rem;font-weight:700;color:#333;">{decision}</div>
                    <div style="margin-top:12px;">
                        <span style="display:inline-block;width:70px;height:70px;border-radius:50%;background:{r_col};line-height:70px;text-align:center;color:white;font-size:1.3rem;font-weight:800;">{r_cn}</span>
                    </div>
                    <div style="color:#888;font-size:0.85rem;margin-top:8px;">置信度 {dp.get('confidence', 80)}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_top_r:
            st.markdown(
                f"""
                <div style="background:white;border-radius:12px;padding:20px;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
                    <table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
                        <tr style="border-bottom:1px solid #eee;"><td style="padding:10px 8px;color:#666;width:90px;">📋 任务类型</td><td style="padding:10px 8px;font-weight:600;color:#333;">{la['task_type']}</td></tr>
                        <tr style="border-bottom:1px solid #eee;"><td style="padding:10px 8px;color:#666;">🎫 操作票号</td><td style="padding:10px 8px;font-weight:600;color:#333;">{la['ticket_no']}</td></tr>
                        <tr style="border-bottom:1px solid #eee;"><td style="padding:10px 8px;color:#666;">🕐 审核时间</td><td style="padding:10px 8px;font-weight:600;color:#333;">{la['timestamp']}</td></tr>
                        <tr><td style="padding:10px 8px;color:#666;">👤 操作员</td><td style="padding:10px 8px;font-weight:600;color:#333;">{st.session_state.get('username') or st.session_state.get('logged_in_user', '未知')}</td></tr>
                    </table>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            f"""
            <div style="background:#f0f4ff;border-radius:10px;padding:16px;margin:16px 0;border-left:4px solid #4a6cf7;">
                <div style="font-weight:700;color:#333;margin-bottom:6px;">📝 操作指令</div>
                <div style="color:#444;line-height:1.8;">{fmt_html(la['user_command'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### 🔍 多智能体审核意见")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                f"""
                <div style="background:#e8f5e9;border-radius:10px;padding:16px;margin:8px 0;border-left:4px solid #4caf50;min-height:120px;">
                    <div style="font-weight:700;color:#2e7d32;margin-bottom:8px;font-size:1rem;">👮 审核员意见</div>
                    <div style="color:#333;line-height:1.7;font-size:0.9rem;">{fmt_html(results.get('auditor', ''))}</div>
                </div>
                <div style="background:#ffebee;border-radius:10px;padding:16px;margin:8px 0;border-left:4px solid #f44336;min-height:120px;">
                    <div style="font-weight:700;color:#c62828;margin-bottom:8px;font-size:1rem;">🥷 红队攻击分析</div>
                    <div style="color:#333;line-height:1.7;font-size:0.9rem;">{fmt_html(results.get('red', ''))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                f"""
                <div style="background:#e3f2fd;border-radius:10px;padding:16px;margin:8px 0;border-left:4px solid #2196f3;min-height:120px;">
                    <div style="font-weight:700;color:#1565c0;margin-bottom:8px;font-size:1rem;">🛡️ 蓝队防御分析</div>
                    <div style="color:#333;line-height:1.7;font-size:0.9rem;">{fmt_html(results.get('blue', ''))}</div>
                </div>
                <div style="background:#fff8e1;border-radius:10px;padding:16px;margin:8px 0;border-left:4px solid #ff9800;min-height:120px;">
                    <div style="font-weight:700;color:#e65100;margin-bottom:8px;font-size:1rem;">📚 规程专家意见</div>
                    <div style="color:#333;line-height:1.7;font-size:0.9rem;">{fmt_html(results.get('expert', ''))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("#### 📋 决策摘要")
        col_v, col_m, col_pdf = st.columns([1, 1, 1])
        ticket_no_pdf = la.get("ticket_no", "N/A")
        record_id_pdf = la.get("record_id", ticket_no_pdf)
        pdf_cache = st.session_state.setdefault("audit_pdf_cache", {})
        pdf_error = None
        pdf_bytes = pdf_cache.get(record_id_pdf)
        if pdf_bytes is None:
            try:
                pdf_bytes = generate_audit_report_pdf(la, results)
                pdf_cache[record_id_pdf] = pdf_bytes
            except Exception as e:
                pdf_error = str(e)

        with col_v:
            violations = dp.get("violations", "无")
            st.markdown(
                f"""
                <div class="audit-summary-card">
                    <div class="audit-summary-title">⚠️ 违反规则</div>
                    <div class="audit-summary-content audit-summary-danger">{fmt_html(violations)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_m:
            measures = dp.get("measures", "无")
            st.markdown(
                f"""
                <div class="audit-summary-card">
                    <div class="audit-summary-title">💡 建议措施</div>
                    <div class="audit-summary-content audit-summary-primary">{fmt_html(measures)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_pdf:
            st.markdown(
                f"""
                <div class="audit-summary-card audit-export-card">
                    <div class="audit-summary-title">📥 导出报告</div>
                    <div class="audit-summary-content audit-summary-muted">报告编号：{fmt_html(record_id_pdf)}</div>
                    <div class="audit-summary-content audit-summary-muted">格式：PDF</div>
                    <div class="audit-summary-content audit-summary-muted">状态：{"已就绪，可直接下载" if pdf_bytes else "生成失败"}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if pdf_bytes:
                st.download_button(
                    label="⬇️ 下载审核报告 PDF",
                    data=pdf_bytes,
                    file_name=f"审核报告_{record_id_pdf}_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"dl_audit_pdf_{record_id_pdf}",
                )
            else:
                st.error(f"PDF 生成失败：{pdf_error}")

        if results.get("rag_results"):
            st.divider()
            st.markdown("#### 📚 RAG 检索相关规程")
            for i, doc in enumerate(results["rag_results"], 1):
                with st.expander(f"📌 {i}. 【{doc['category']}】{doc['title']}（相关度：{doc['score']:.2f}）"):
                    st.markdown(doc["content"])

        with st.expander("⭐ 完整决策理由", expanded=False):
            st.markdown(results.get("decision", ""))

        if risk == "HIGH":
            st.markdown(
                """
                <div style="background:#ffebee;border:2px solid #ef4444;border-radius:10px;padding:16px;margin:16px 0;text-align:center;">
                    <div style="font-size:1.2rem;font-weight:800;color:#c62828;">⚠️ 高危操作警告</div>
                    <div style="color:#c62828;margin-top:8px;">此操作具有高风险，请严格执行操作票与监护制度，经主管领导审批后方可执行。</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
