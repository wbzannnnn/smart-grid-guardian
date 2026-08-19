import json

import pandas as pd
import streamlit as st

from ui_helpers import render_page_title


def render_knowledge_base_page(*, get_kb):
    render_page_title("assets/kb_page.css", "kb-title", "📚 知识库管理")

    try:
        kb = get_kb()
    except Exception as e:
        st.error(f"❌ 知识库初始化失败：{e}")
        st.stop()

    stats = kb.get_stats()
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        st.metric("规程总数", stats["total"])
    with col_s2:
        st.metric("内置规程", stats["by_source"].get("builtin", 0))
    with col_s3:
        st.metric("自定义规程", stats["by_source"].get("user", 0))

    tab_list, tab_add, tab_stats = st.tabs(["📋 规程列表", "➕ 添加规程", "📊 分类统计"])

    with tab_list:
        docs = kb.list_docs()
        if docs:
            search_kw = st.text_input("🔍 搜索规程", placeholder="输入关键词搜索", key="kb_search")
            if search_kw:
                docs = [d for d in docs if search_kw.lower() in (d["title"] + d["content"]).lower()]
            st.markdown(f"共 {len(docs)} 条")
            for doc in docs:
                with st.expander(f"【{doc['category']}】{doc['title']} [{doc['source']}]"):
                    st.markdown(doc["content"])
                    col_del, _ = st.columns([1, 4])
                    with col_del:
                        if doc["source"] == "user":
                            if st.button("🗑️ 删除", key=f"del_{doc['id']}"):
                                kb.delete_doc(doc["id"])
                                st.success("已删除")
                                st.rerun()
        else:
            st.info("暂无规程")

    with tab_add:
        with st.form("add_doc_form", clear_on_submit=True):
            st.markdown("**➕ 添加自定义规程**")
            add_cat = st.selectbox("规程类别", ["通用安全规程", "五防规则", "倒闸操作", "应急预案", "其他"], key="add_cat")
            add_title = st.text_input("规程标题", placeholder="如：电容器操作安全规程", key="add_title")
            add_content = st.text_area("规程内容", placeholder="请输入完整的规程内容...", height=200, key="add_content")
            submitted = st.form_submit_button("📤 提交入库", type="primary", use_container_width=True)
            if submitted:
                if add_title and add_content:
                    kb.add_doc(add_cat, add_title, add_content)
                    st.success("✅ 规程已添加并重新索引！")
                    st.rerun()
                else:
                    st.warning("⚠️ 请填写标题和内容")

        with st.expander("📄 批量导入（JSON）", expanded=False):
            json_input = st.text_area("粘贴 JSON 数组格式的规程数据", height=150, key="json_import")
            if st.button("📥 批量导入", key="import_btn"):
                try:
                    items = json.loads(json_input)
                    for item in items:
                        kb.add_doc(item.get("category", "其他"), item.get("title", ""), item.get("content", ""))
                    st.success(f"✅ 成功导入 {len(items)} 条规程！")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ JSON 解析失败：{e}")

    with tab_stats:
        st.markdown("**📊 规程分类统计**")
        if stats["by_category"]:
            df_cat = pd.DataFrame([
                {"规程类别": k, "数量": v} for k, v in stats["by_category"].items()
            ])
            st.bar_chart(df_cat.set_index("规程类别"))
        st.markdown("**📄 最近添加的规程**")
        recent = kb.list_docs()[:5]
        for doc in recent:
            st.markdown(f"- 【{doc['category']}】{doc['title']}（{doc['created_at'][:10]}）")
