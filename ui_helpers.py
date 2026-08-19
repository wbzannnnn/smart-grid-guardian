import os

import streamlit as st


_BASE_DIR = os.path.dirname(__file__)


def inject_css_file(relative_path: str) -> None:
    """从独立 CSS 文件加载样式。"""
    css_path = os.path.join(_BASE_DIR, relative_path)
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>\n{f.read()}\n</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning(f"样式文件缺失：{relative_path}")


def render_page_title(css_path: str, class_name: str, title_html: str) -> None:
    """注入页面样式并渲染统一标题。"""
    inject_css_file(css_path)
    st.markdown(f'<h2 class="{class_name}">{title_html}</h2>', unsafe_allow_html=True)
