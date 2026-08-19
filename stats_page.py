from datetime import datetime

import pandas as pd
import streamlit as st

from ui_helpers import render_page_title


def render_stats_page(*, get_audit_stats, get_audit_records):
    render_page_title("assets/stats_page.css", "stats-title", "📈 统计分析")

    try:
        stats = get_audit_stats()
    except Exception:
        stats = {"total": 0, "allow": 0, "deny": 0, "avg_confidence": 0, "today": 0}

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总审核数", stats["total"])
    with col2:
        st.metric("今日审核", stats["today"])
    with col3:
        st.metric("✅ 通过", stats["allow"])
    with col4:
        st.metric("平均置信度", f"{stats['avg_confidence']:.1f}%")

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.metric("❌ 拒绝操作", stats["deny"])
    with col_r2:
        deny_rate = (stats["deny"] / stats["total"] * 100) if stats["total"] > 0 else 0
        st.metric("拒绝率", f"{deny_rate:.1f}%")

    st.divider()

    try:
        records = get_audit_records(limit=500)
    except Exception:
        records = []

    tab_overview, tab_trend, tab_detail = st.tabs(["📊 总览", "📈 趋势分析", "📋 明细记录"])

    with tab_overview:
        if records:
            st.subheader("🔍 审核决策分布")
            col_oc1, col_oc2 = st.columns(2)

            allow_cnt = sum(1 for r in records if r.get("decision") == "ALLOW")
            deny_cnt = sum(1 for r in records if r.get("decision") == "DENY")
            pie_data = pd.DataFrame({
                "决策": ["✅ 通过 (ALLOW)", "❌ 拒绝 (DENY)"],
                "数量": [allow_cnt, deny_cnt],
            })

            with col_oc1:
                st.write("**审核决策分布**")
                st.bar_chart(pie_data.set_index("决策"))

            risk_counts = {}
            for r in records:
                rl = r.get("risk_level", "MEDIUM")
                risk_counts[rl] = risk_counts.get(rl, 0) + 1
            risk_df = pd.DataFrame([
                {"风险等级": k, "数量": v} for k, v in risk_counts.items()
            ])
            with col_oc2:
                st.write("**风险等级分布**")
                if not risk_df.empty:
                    st.bar_chart(risk_df.set_index("风险等级"))
                else:
                    st.info("暂无数据")

            st.subheader("📂 操作类型分布")
            task_counts = {}
            for r in records:
                tt = r.get("task_type", "其他操作")
                task_counts[tt] = task_counts.get(tt, 0) + 1
            task_df = pd.DataFrame([
                {"操作类型": k, "审核次数": v} for k, v in sorted(task_counts.items(), key=lambda x: -x[1])
            ])
            if not task_df.empty:
                st.bar_chart(task_df.set_index("操作类型"))
            else:
                st.info("暂无数据")

            st.subheader("🎯 置信度分布")
            conf_bins = {"0-20%": 0, "21-40%": 0, "41-60%": 0, "61-80%": 0, "81-100%": 0}
            for r in records:
                conf = r.get("confidence", 50)
                if conf <= 20:
                    conf_bins["0-20%"] += 1
                elif conf <= 40:
                    conf_bins["21-40%"] += 1
                elif conf <= 60:
                    conf_bins["41-60%"] += 1
                elif conf <= 80:
                    conf_bins["61-80%"] += 1
                else:
                    conf_bins["81-100%"] += 1
            conf_df = pd.DataFrame([{"置信度区间": k, "次数": v} for k, v in conf_bins.items()])
            if conf_df["次数"].sum() > 0:
                st.bar_chart(conf_df.set_index("置信度区间"))
            else:
                st.info("暂无置信度数据")

            st.subheader("👥 操作员审核统计")
            op_counts = {}
            for r in records:
                op = r.get("operator", "未知")
                op_counts[op] = op_counts.get(op, 0) + 1
            op_df = pd.DataFrame([
                {"操作员": k, "审核次数": v} for k, v in sorted(op_counts.items(), key=lambda x: -x[1])
            ])
            if not op_df.empty:
                st.dataframe(op_df, use_container_width=True, hide_index=True)
            else:
                st.info("暂无操作员数据")
        else:
            st.info("暂无审核数据，无法进行统计分析。")

    with tab_trend:
        if records:
            date_counts = {}
            for r in records:
                ts = r.get("created_at", "") or r.get("timestamp", "")
                if ts:
                    date_key = ts[:10]
                    if date_key not in date_counts:
                        date_counts[date_key] = {"total": 0, "allow": 0, "deny": 0}
                    date_counts[date_key]["total"] += 1
                    decision = r.get("decision", "ALLOW")
                    if decision == "ALLOW":
                        date_counts[date_key]["allow"] += 1
                    else:
                        date_counts[date_key]["deny"] += 1

            if date_counts:
                sorted_dates = sorted(date_counts.keys())
                trend_df = pd.DataFrame([
                    {
                        "日期": d,
                        "总审核数": date_counts[d]["total"],
                        "通过数": date_counts[d]["allow"],
                        "拒绝数": date_counts[d]["deny"],
                    }
                    for d in sorted_dates[-30:]
                ])
                st.line_chart(trend_df.set_index("日期"))
            else:
                st.info("暂无趋势数据")

            st.subheader("🔴 风险等级趋势")
            risk_trend = {}
            for r in records:
                ts = r.get("created_at", "") or r.get("timestamp", "")
                if ts:
                    date_key = ts[:10]
                    rl = r.get("risk_level", "MEDIUM")
                    if date_key not in risk_trend:
                        risk_trend[date_key] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
                    risk_trend[date_key][rl] = risk_trend[date_key].get(rl, 0) + 1

            if risk_trend:
                sorted_risk_dates = sorted(risk_trend.keys())
                risk_trend_df = pd.DataFrame([
                    {
                        "日期": d,
                        "高风险": risk_trend[d].get("HIGH", 0),
                        "中风险": risk_trend[d].get("MEDIUM", 0),
                        "低风险": risk_trend[d].get("LOW", 0),
                    }
                    for d in sorted_risk_dates[-30:]
                ])
                st.line_chart(risk_trend_df.set_index("日期"))
            else:
                st.info("暂无风险趋势数据")

            st.subheader("📉 每日拒绝率趋势")
            if date_counts:
                deny_rate_data = []
                for d in sorted(date_counts.keys())[-30:]:
                    total = date_counts[d]["total"]
                    deny = date_counts[d]["deny"]
                    rate = (deny / total * 100) if total > 0 else 0
                    deny_rate_data.append({"日期": d, "拒绝率(%)": round(rate, 1)})
                if deny_rate_data:
                    st.line_chart(pd.DataFrame(deny_rate_data).set_index("日期"))
        else:
            st.info("暂无数据用于趋势分析")

    with tab_detail:
        st.subheader("📋 审核记录明细")
        if records:
            df_records = pd.DataFrame([
                {
                    "审核ID": r.get("record_id", ""),
                    "操作指令": (r.get("command", "") or "")[:50] + ("..." if len(r.get("command", "") or "") > 50 else ""),
                    "决策": r.get("decision", ""),
                    "风险等级": r.get("risk_level", ""),
                    "置信度": r.get("confidence", 0),
                    "操作员": r.get("operator", ""),
                    "时间": (r.get("created_at", "") or r.get("timestamp", ""))[:19],
                }
                for r in records
            ])
            st.dataframe(df_records, use_container_width=True, hide_index=True)

            csv = df_records.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="📥 导出CSV",
                data=csv,
                file_name=f"审核记录_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("暂无审核记录")
