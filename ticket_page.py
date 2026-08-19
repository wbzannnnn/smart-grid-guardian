import json
from datetime import datetime

import streamlit as st
from langchain_openai import ChatOpenAI

from ui_helpers import render_page_title


def render_ticket_page(
    *,
    model_name: str,
    api_key: str,
    api_base_url: str,
    save_operation_ticket,
    get_operation_tickets,
    generate_operation_ticket_pdf,
    pdf_available: bool,
):
    render_page_title("assets/ticket_page.css", "ticket-title", "📝 智能操作票管理")

    st.info("**📋 依据规范：** 《电力安全工作规程》（GB 26860-2011）、《电力变压器操作规程》（DL 572-2010）")

    tab_gen, tab_list, tab_templates = st.tabs(["📝 生成操作票", "📋 操作票列表", "📑 标准票库"])

    with tab_gen:
        selected_template = st.session_state.pop("selected_template", None)
        template_task = selected_template.get("task", "") if selected_template else ""
        template_type = selected_template.get("type", "") if selected_template else ""

        if selected_template:
            st.success(f"已从标准票库加载模板：{selected_template['name']}，请完善操作信息")

        st.subheader("📄 操作票基本信息")
        col_basic1, col_basic2 = st.columns(2)
        with col_basic1:
            ticket_type_opts = ["第一种工作票", "第二种工作票", "倒闸操作票", "紧急抢修单"]
            ticket_type_idx = ticket_type_opts.index(template_type) if template_type in ticket_type_opts else 0
            ticket_type = st.selectbox("操作票类型", ticket_type_opts, index=ticket_type_idx, help="根据规范选择操作票类型")
            station_name = st.text_input("变电站名称", value=st.session_state.get("station_name", "110kV 城东变电站"), help="填写所属变电站名称")
        with col_basic2:
            task_type_opts = ["线路停送电", "主变停送电", "母线倒闸", "电容器投切", "开关检修", "接地刀闸操作", "其他操作"]
            task_type_idx = 0
            if template_task and template_task in task_type_opts:
                task_type_idx = task_type_opts.index(template_task)
            task_type = st.selectbox("操作任务类型", task_type_opts, index=task_type_idx, help="选择本次操作的任务类型")
            voltage_level = st.selectbox("电压等级", ["110kV", "35kV", "10kV", "0.4kV"], help="操作设备的电压等级")

        st.subheader("🔧 操作设备信息")
        col_dev1, col_dev2, col_dev3 = st.columns(3)
        with col_dev1:
            equipment_name = st.text_input("设备名称", placeholder="如：10kV 101 开关", help="填写设备完整名称")
        with col_dev2:
            equipment_no = st.text_input("设备编号", placeholder="如：101", help="填写设备编号")
        with col_dev3:
            location = st.text_input("设备位置", placeholder="如：#1主变高压侧", help="填写设备所在位置")

        st.subheader("📝 操作任务")
        col_cmd1, col_cmd2 = st.columns(2)
        with col_cmd1:
            current_status = st.selectbox("操作前状态", ["运行", "热备用", "冷备用", "检修", "接地"], help="设备当前运行状态")
        with col_cmd2:
            target_status = st.selectbox("操作后状态", ["运行", "热备用", "冷备用", "检修", "接地"], help="操作完成后的目标状态")

        user_command = st.text_area(
            "操作指令描述",
            placeholder="请使用标准调度术语输入，如：10kV 101 线路由运行转检修",
            height=80,
            help="使用规范的调度操作术语，明确操作任务",
        )

        st.subheader("⚠️ 危险点分析与预控措施")
        hazard_analysis = st.text_area(
            "危险点分析",
            placeholder="填写操作中可能存在的危险点，如：\n1. 带负荷拉合刀闸\n2. 带电挂接地线\n3. 误操作设备\n4. 人身触电风险",
            height=80,
            key="hazard_input",
        )
        prevention_measures = st.text_area(
            "预控措施",
            placeholder="填写相应的预控措施，如：\n1. 严格执行监护制度\n2. 操作前核对设备双重名称\n3. 使用合格的安全工器具\n4. 保持安全距离",
            height=80,
            key="prevention_input",
        )

        st.subheader("👥 操作人员安排")
        col_person1, col_person2, col_person3 = st.columns(3)
        with col_person1:
            operator = st.text_input("操作人", value=st.session_state.get("logged_in_user", ""), help="执行操作的人员")
        with col_person2:
            supervisor = st.text_input("监护人", placeholder="由经验丰富的值班员担任", help="监督操作的人员")
        with col_person3:
            approver = st.text_input("值班负责人", placeholder="值班长或站长", help="审核批准操作票的人员")

        st.markdown(
            """
            <div class="warning-box">
                <strong>⚡ 操作票填写规范（依据 GB 26860-2011）：</strong><br/>
                • 每张操作票只能填写 <strong>一个</strong> 操作任务<br/>
                • 操作票应使用规范调度术语，逐项填写，不得漏项、倒项<br/>
                • 操作前必须核对设备 <strong>双重名称</strong>（设备名称和编号）及位置<br/>
                • 必须由 <strong>两人</strong> 执行操作，一人操作，一人监护<br/>
                • 操作中发生疑问应立即停止操作并报告值班负责人<br/>
                • 操作票填写后应由监护人和值班负责人审核签名
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_gen, col_reset = st.columns([2, 1])
        with col_gen:
            if st.button("🧠 生成标准操作票", type="primary", use_container_width=True, key="gen_ticket"):
                if user_command and operator and supervisor:
                    with st.spinner("⚡ 依据电力安全规程生成标准操作票..."):
                        try:
                            ticket_no = f"OP{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            llm = ChatOpenAI(
                                model=model_name,
                                openai_api_key=api_key,
                                openai_api_base=api_base_url,
                                temperature=0.2,
                                max_tokens=2000,
                                timeout=60,
                            )
                            prompt = f"""你是变电站操作票生成专家，精通《电力安全工作规程》(GB 26860-2011)和《电力变压器操作规程》(DL 572-2010)。

请根据以下信息生成符合国家标准的电气操作票：

【基本信息】
- 操作票类型：{ticket_type}
- 变电站：{station_name}
- 电压等级：{voltage_level}
- 操作设备：{equipment_name} ({equipment_no})
- 设备位置：{location}
- 操作前状态：{current_status}
- 操作后状态：{target_status}
- 操作指令：{user_command}

【危险点分析】
{hazard_analysis or '依据操作类型自动分析'}

【预控措施】
{prevention_measures or '依据危险点制定'}

【操作人员】
- 操作人：{operator}
- 监护人：{supervisor}
- 值班负责人：{approver or "待安排"}

请严格按照以下要求返回 JSON：
1. 包含 steps 数组和 precautions 数组
2. steps 每项包含：step_no、operation、check_point
3. precautions 每项包含：no、hazard、measure
4. 只返回 JSON，不要其他文字"""

                            steps_msg = llm.invoke(prompt)
                            steps_text = steps_msg.content if hasattr(steps_msg, "content") else str(steps_msg)
                            steps_data = []
                            try:
                                parsed = json.loads(steps_text)
                                steps_data = parsed.get("steps", [])
                            except Exception:
                                lines = [l.strip() for l in steps_text.split("\n") if l.strip()]
                                for i, line in enumerate(lines[:15]):
                                    if line and (line[0].isdigit() or "操作" in line or "检查" in line):
                                        steps_data.append({"step_no": i + 1, "operation": line, "check_point": "已确认"})

                            ticket_data = {
                                "ticket_no": ticket_no,
                                "ticket_type": ticket_type,
                                "task_type": task_type,
                                "station_name": station_name,
                                "voltage_level": voltage_level,
                                "equipment_name": equipment_name,
                                "equipment_no": equipment_no,
                                "location": location,
                                "current_status": current_status,
                                "target_status": target_status,
                                "command": user_command,
                                "hazard_analysis": hazard_analysis,
                                "prevention_measures": prevention_measures,
                                "operator": operator,
                                "supervisor": supervisor,
                                "approver": approver or "待安排",
                                "steps": json.dumps(steps_data, ensure_ascii=False),
                                "status": "草稿",
                                "created_by": st.session_state.get("logged_in_user", operator),
                                "created_at": datetime.now().isoformat(),
                                "updated_at": datetime.now().isoformat(),
                            }
                            save_operation_ticket(ticket_data)

                            st.success(f"✅ 操作票生成成功！编号：{ticket_no}")
                            st.markdown("---")
                            st.markdown(f'<div class="ticket-header">电气操作票（第 {ticket_no} 号）</div>', unsafe_allow_html=True)

                            col_preview1, col_preview2 = st.columns(2)
                            with col_preview1:
                                st.markdown(f"**变电站：** {station_name}")
                                st.markdown(f"**电压等级：** {voltage_level}")
                                st.markdown(f"**操作设备：** {equipment_name} ({equipment_no})")
                                st.markdown(f"**操作前状态：** {current_status} → **操作后状态：** {target_status}")
                            with col_preview2:
                                st.markdown(f"**操作人：** {operator}")
                                st.markdown(f"**监护人：** {supervisor}")
                                st.markdown(f"**值班负责人：** {approver or '待安排'}")

                            st.markdown(f"**操作任务：** {user_command}")
                            if steps_data:
                                st.markdown("**操作步骤：**")
                                for step in steps_data:
                                    if isinstance(step, dict):
                                        st.markdown(
                                            f"""
                                            <div class="step-row">
                                                <div class="step-num">{step.get('step_no', '')}</div>
                                                <div class="step-content">
                                                    <div><strong>{step.get('operation', '')}</strong></div>
                                                    <div style="color:#666;font-size:0.85rem;">✓ 检查点：{step.get('check_point', '已确认')}</div>
                                                </div>
                                            </div>
                                            """,
                                            unsafe_allow_html=True,
                                        )
                                    else:
                                        st.markdown(f"• {step}")

                            if pdf_available:
                                try:
                                    pdf_bytes = generate_operation_ticket_pdf(ticket_data)
                                    st.download_button(
                                        "⬇️ 下载操作票 PDF",
                                        data=pdf_bytes,
                                        file_name=f"操作票_{ticket_no}.pdf",
                                        mime="application/pdf",
                                        use_container_width=True,
                                    )
                                except Exception:
                                    pass
                        except Exception as e:
                            st.error(f"❌ 生成失败：{e}")
                else:
                    if not user_command:
                        st.warning("⚠️ 请填写操作指令描述")
                    if not operator:
                        st.warning("⚠️ 请填写操作人")
                    if not supervisor:
                        st.warning("⚠️ 请填写监护人")
        with col_reset:
            if st.button("🔄 重置", use_container_width=True):
                st.rerun()

    with tab_list:
        col_filter1, col_filter2, col_filter3 = st.columns(3)
        with col_filter1:
            filter_status = st.multiselect("状态筛选", ["草稿", "待审核", "已批准", "执行中", "已完成", "已作废"], default=["草稿", "待审核", "已批准", "执行中", "已完成"], help="筛选特定状态的操作票")
        with col_filter2:
            filter_type = st.multiselect("类型筛选", ["第一种工作票", "第二种工作票", "倒闸操作票", "紧急抢修单"], help="筛选特定类型的操作票")
        with col_filter3:
            search_key = st.text_input("🔍 搜索", placeholder="票号/设备名称", help="搜索操作票")

        try:
            tickets = get_operation_tickets(limit=100)
            if tickets:
                status_colors = {"草稿": "#fef3c7", "待审核": "#dbeafe", "已批准": "#d1fae5", "执行中": "#ede9fe", "已完成": "#d1fae5", "已作废": "#fee2e2"}
                status_text_colors = {"草稿": "#92400e", "待审核": "#1e40af", "已批准": "#065f46", "执行中": "#5b21b6", "已完成": "#065f46", "已作废": "#991b1b"}

                filtered_tickets = []
                for t in tickets:
                    status = t.get("status", "草稿")
                    ticket_type_val = t.get("ticket_type", "")
                    if status in filter_status:
                        if not filter_type or ticket_type_val in filter_type:
                            if not search_key or search_key.lower() in str(t.get("ticket_no", "")).lower() or search_key.lower() in str(t.get("equipment_name", "")).lower():
                                filtered_tickets.append(t)

                st.markdown(f"**共 {len(filtered_tickets)} 张操作票**")

                col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                status_counts = {}
                for t in tickets:
                    s = t.get("status", "草稿")
                    status_counts[s] = status_counts.get(s, 0) + 1
                with col_stat1:
                    st.metric("总票数", len(tickets))
                with col_stat2:
                    st.metric("执行中", status_counts.get("执行中", 0))
                with col_stat3:
                    st.metric("已完成", status_counts.get("已完成", 0))
                with col_stat4:
                    st.metric("已作废", status_counts.get("已作废", 0))

                st.divider()
                for ticket in reversed(filtered_tickets):
                    status = ticket.get("status", "草稿")
                    bg_color = status_colors.get(status, "#f1f5f9")
                    text_color = status_text_colors.get(status, "#374151")
                    ticket_no = ticket.get("ticket_no", "")

                    with st.container():
                        st.markdown(
                            f"""
                            <div style="background:white;border-radius:12px;padding:16px;margin:8px 0;box-shadow:0 2px 8px rgba(0,0,0,0.06);border-left:4px solid {text_color};">
                                <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                                    <div>
                                        <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
                                            <span style="font-weight:700;color:#1e40af;font-size:1.1rem;">{ticket_no}</span>
                                            <span class="status-badge" style="background:{bg_color};color:{text_color};">{status}</span>
                                            <span style="color:#64748b;font-size:0.85rem;">{ticket.get('ticket_type', '')}</span>
                                        </div>
                                        <div style="color:#374151;font-size:0.95rem;margin-bottom:6px;"><strong>设备：</strong>{ticket.get('equipment_name', '')} ({ticket.get('equipment_no', '')}) <span style="margin-left:15px;"><strong>电压：</strong>{ticket.get('voltage_level', '')}</span></div>
                                        <div style="color:#374151;font-size:0.95rem;margin-bottom:6px;"><strong>操作：</strong>{ticket.get('command', '')}</div>
                                        <div style="display:flex;gap:20px;color:#64748b;font-size:0.85rem;"><span>👤 操作人：{ticket.get('operator', '')}</span><span>👀 监护人：{ticket.get('supervisor', '')}</span><span>🕒 {ticket.get('created_at', '')[:10]}</span></div>
                                    </div>
                                    <div style="display:flex;gap:8px;flex-shrink:0;"><span style="background:#fef3c7;color:#92400e;padding:3px 10px;border-radius:6px;font-size:0.8rem;">{ticket.get('task_type', '')}</span></div>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        col_act1, col_act2, col_act3, col_act4 = st.columns(4)
                        with col_act1:
                            if st.button("👁️ 查看", key=f"view_{ticket_no}", use_container_width=True):
                                st.session_state[f"view_ticket_{ticket_no}"] = not st.session_state.get(f"view_ticket_{ticket_no}", False)
                        with col_act2:
                            if status == "草稿":
                                if st.button("📤 提交审核", key=f"submit_{ticket_no}", use_container_width=True):
                                    ticket["status"] = "待审核"
                                    save_operation_ticket(ticket)
                                    st.success("已提交审核")
                                    st.rerun()
                            elif status == "待审核":
                                if st.button("✅ 批准", key=f"approve_{ticket_no}", use_container_width=True):
                                    ticket["status"] = "已批准"
                                    save_operation_ticket(ticket)
                                    st.success("已批准")
                                    st.rerun()
                            elif status == "已批准":
                                if st.button("▶️ 开始执行", key=f"execute_{ticket_no}", use_container_width=True):
                                    ticket["status"] = "执行中"
                                    save_operation_ticket(ticket)
                                    st.success("操作开始执行")
                                    st.rerun()
                            elif status == "执行中":
                                if st.button("✅ 完成操作", key=f"complete_{ticket_no}", use_container_width=True):
                                    ticket["status"] = "已完成"
                                    save_operation_ticket(ticket)
                                    st.success("操作已完成")
                                    st.rerun()
                        with col_act3:
                            if st.button("⬇️ 下载", key=f"download_{ticket_no}", use_container_width=True):
                                if pdf_available:
                                    try:
                                        pdf_bytes = generate_operation_ticket_pdf(ticket)
                                        st.download_button("下载 PDF", data=pdf_bytes, file_name=f"操作票_{ticket_no}.pdf", mime="application/pdf", key=f"pdf_{ticket_no}")
                                    except Exception:
                                        st.info("PDF 生成功能暂不可用")
                        with col_act4:
                            if status not in ["执行中", "已完成"]:
                                if st.button("❌ 作废", key=f"cancel_{ticket_no}", use_container_width=True):
                                    ticket["status"] = "已作废"
                                    save_operation_ticket(ticket)
                                    st.success("操作票已作废")
                                    st.rerun()

                        if st.session_state.get(f"view_ticket_{ticket_no}", False):
                            try:
                                steps = ticket.get("steps", "[]")
                                steps_data = json.loads(steps) if isinstance(steps, str) else steps
                            except Exception:
                                steps_data = []
                            with st.expander(f"操作票详情：{ticket_no}", expanded=True):
                                st.markdown(f"**变电站：** {ticket.get('station_name', '')}")
                                st.markdown(f"**位置：** {ticket.get('location', '')}")
                                st.markdown(f"**预控措施：** {ticket.get('prevention_measures', '')}")
                                if steps_data:
                                    st.markdown("**操作步骤：**")
                                    for step in steps_data:
                                        if isinstance(step, dict):
                                            st.markdown(f"{step.get('step_no', '')}. {step.get('operation', '')}")
                                        else:
                                            st.markdown(f"- {step}")
                        st.markdown("---")
            else:
                st.info("📭 暂无操作票记录")
        except Exception as e:
            st.warning(f"加载失败：{e}")

    with tab_templates:
        st.subheader("📑 标准操作票模板库")
        st.markdown("根据《电力安全工作规程》和实际运行经验，提供以下标准操作票模板。")

        templates = [
            {"name": "线路停送电操作票", "type": "倒闸操作票", "task": "线路停送电", "desc": "适用于 10kV/35kV/110kV 线路的停电和送电操作", "steps": ["接收调度指令", "填写操作票", "审核批准", "模拟预演", "核对设备", "逐项操作", "检查确认", "汇报记录"]},
            {"name": "主变压器停送电操作票", "type": "倒闸操作票", "task": "主变停送电", "desc": "适用于主变压器的停电和送电操作", "steps": ["接收调度指令", "核对保护定值", "填写操作票", "操作前检查", "执行操作", "带负荷测试", "状态确认", "汇报记录"]},
            {"name": "母线倒闸操作票", "type": "倒闸操作票", "task": "母线倒闸", "desc": "适用于母线之间的倒闸操作", "steps": ["接收调度指令", "退出自动装置", "备用母线充电", "合上母联", "倒负荷", "切换保护", "状态确认", "投入自动装置"]},
            {"name": "开关检修工作票", "type": "第一种工作票", "task": "开关检修", "desc": "适用于断路器检修时的安全措施", "steps": ["停电申请", "核对设备", "拉开开关", "拉开刀闸", "验电接地", "装设遮栏", "悬挂标示牌", "工作许可"]},
            {"name": "电容器投切操作票", "type": "倒闸操作票", "task": "电容器投切", "desc": "适用于无功补偿电容器的投切操作", "steps": ["接收指令", "检查电容器状态", "合上开关", "检查电流", "记录数据", "汇报完成"]},
            {"name": "接地刀闸操作票", "type": "倒闸操作票", "task": "接地刀闸操作", "desc": "适用于接地刀闸的分合操作", "steps": ["核对设备", "确认无电压", "操作接地刀闸", "检查位置", "记录时间"]},
        ]

        for template in templates:
            with st.expander(f"📋 {template['name']}（{template['type']}）"):
                st.markdown(f"**说明：** {template['desc']}")
                st.markdown("**标准操作步骤：**")
                for i, step in enumerate(template["steps"], 1):
                    st.markdown(f"{i}. {step}")
                if st.button(f"📝 使用此模板", key=f"use_{template['name']}"):
                    st.session_state.selected_template = template
                    st.session_state.current_page = "操作票管理"
                    st.rerun()
