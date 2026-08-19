import streamlit as st
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ui_helpers import render_page_title


def render_qa_page(*, get_kb, model_name: str, api_key: str, api_base_url: str):
    render_page_title("assets/qa_page.css", "qa-title", "💬 规程智能问答（RAG 检索增强生成）")

    try:
        kb = get_kb()
        kb_stats = kb.get_stats()
        st.markdown(
            f"""
            <div class="spec-box">
                <strong>📚 知识库状态：</strong>
                规程总数 <b>{kb_stats['total']}</b> 条，
                分类：{'、'.join([f"{k}({v}条)" for k, v in kb_stats['by_category'].items()])}
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.warning(f"⚠️ 知识库加载失败：{e}")
        kb = None

    st.markdown("**🔍 请描述您的问题（支持自然语言）：**")
    q_examples = [
        "带负荷拉隔离开关会有什么后果？",
        "操作前需要做哪些准备？",
        "验电的标准步骤是什么？",
        "如何正确挂接地线？",
        "线路停电的操作顺序是什么？",
    ]
    eg_cols = st.columns(5)
    for i, eg in enumerate(q_examples):
        with eg_cols[i]:
            if st.button(f"📌 {eg[:10]}...", key=f"qeg_{i}", help=eg):
                st.session_state.qa_question = eg

    question = st.text_area(
        "输入问题",
        value=st.session_state.get("qa_question", ""),
        placeholder="如：操作前需要做哪些准备？验电的步骤是什么？",
        height=80,
        key="qa_input",
    )

    col_qa_run, col_qa_kb = st.columns([3, 1])
    with col_qa_run:
        top_k = st.slider("检索条数", 2, 8, 4, key="qa_topk")
        use_embed = st.checkbox("使用 LLM Embedding（更精准，需 API）", value=False, key="qa_use_embed")
    with col_qa_kb:
        st.markdown("")
        run_qa = st.button("🔎 检索并回答", type="primary", use_container_width=True, key="qa_run")

    if run_qa and question:
        with st.spinner("⚡ 正在检索相关规程..."):
            try:
                retrieved = kb.search(question, top_k=top_k, use_llm_embed=use_embed) if kb else []
                st.markdown("**📄 检索到的相关规程：**")
                for i, doc in enumerate(retrieved, 1):
                    with st.expander(f"📌 {i}. 【{doc['category']}】{doc['title']}（相关度：{doc['score']:.2f}）"):
                        st.markdown(doc["content"])

                if retrieved:
                    context = "\n\n---\n\n".join([
                        f"【{d['category']}】{d['title']}：\n{d['content']}"
                        for d in retrieved
                    ])
                else:
                    context = "（未检索到相关规程，基于通用知识回答）"

                with st.spinner("🤖 大模型生成回答中..."):
                    qa_llm = ChatOpenAI(
                        model=model_name,
                        openai_api_key=api_key,
                        openai_api_base=api_base_url,
                        temperature=0.3,
                        max_tokens=1200,
                        timeout=60,
                    )
                    qa_prompt = f"""你是一个严谨的电力安全规程专家。请根据以下检索到的相关规程内容，准确回答用户问题。

【相关规程】
{context}

【用户问题】
{question}

回答要求：
1. 先引用相关规程条款，再给出具体建议
2. 答案要专业、准确、有据可查
3. 如检索结果不足以回答，请明确说明
4. 重点提醒安全注意事项"""
                    try:
                        qa_response = (
                            ChatPromptTemplate.from_messages([("human", qa_prompt)])
                            | qa_llm
                            | StrOutputParser()
                        ).invoke({})
                    except Exception as e:
                        qa_response = f"问答服务调用失败：{str(e)}"
            except Exception as e:
                st.error(f"❌ 问答失败：{str(e)}")
                qa_response = None

            if qa_response:
                st.markdown("---")
                st.subheader("💡 智能回答：")
                st.success(qa_response)

    if "qa_history" not in st.session_state:
        st.session_state.qa_history = []
    if st.session_state.qa_history:
        st.divider()
        st.markdown("**📋 历史问答：**")
        for h in reversed(st.session_state.qa_history[-5:]):
            with st.expander(f"Q: {h['q'][:40]}..."):
                st.markdown(f"**Q：**{h['q']}")
                st.markdown(f"**A：**{h['a']}")

    if run_qa and question:
        st.session_state.qa_history.append({"q": question, "a": qa_response if "qa_response" in locals() else ""})
        st.session_state.qa_question = ""
