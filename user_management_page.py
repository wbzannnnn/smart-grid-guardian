import hashlib

import pandas as pd
import streamlit as st

from ui_helpers import render_page_title


def render_user_management_page(
    *,
    get_all_users,
    delete_user,
    update_user_password,
    add_user,
    verify_user,
    get_app_db,
):
    if st.session_state.get("user_role") != "管理员":
        st.error("⚠️ 仅管理员可访问此页面")
        st.stop()

    render_page_title("assets/user_page.css", "user-title", "👥 用户管理")

    tab_u_list, tab_u_add = st.tabs(["📋 用户列表", "➕ 添加用户"])

    with tab_u_list:
        users = get_all_users()
        if users:
            df_users = pd.DataFrame([
                {
                    "ID": u["id"],
                    "用户名": u["username"],
                    "角色": u["role"],
                    "显示名": u.get("display_name", ""),
                    "工号": u.get("employee_id", ""),
                    "电话": u.get("phone", ""),
                    "状态": "✅ 启用" if u.get("is_active", 1) else "❌ 禁用",
                    "创建时间": u.get("created_at", "")[:10],
                    "最后登录": u.get("last_login", "从未")[:10] if u.get("last_login") else "从未",
                }
                for u in users
            ])
            st.dataframe(df_users, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🔧 用户操作")
            op_col1, op_col2, op_col3 = st.columns(3)
            with op_col1:
                del_user_id = st.number_input("输入用户ID删除", min_value=1, step=1, key="del_user_id")
                if st.button("🗑️ 删除用户", type="secondary"):
                    if del_user_id == 1:
                        st.warning("不能删除管理员账号")
                    else:
                        delete_user(del_user_id)
                        st.success("用户已禁用")
                        st.rerun()
            with op_col2:
                chg_pwd_id = st.number_input("用户ID", min_value=1, step=1, key="chg_pwd_id")
                new_pwd = st.text_input("新密码", type="password", key="chg_pwd_val")
                if st.button("🔑 修改密码", type="secondary"):
                    if new_pwd and len(new_pwd) >= 4:
                        update_user_password(chg_pwd_id, new_pwd)
                        st.success("密码已更新")
                        st.rerun()
                    else:
                        st.warning("密码长度至少4位")
            with op_col3:
                st.info("💡 提示：管理员ID为1，不可删除")

    with tab_u_add:
        with st.form("add_user_form", clear_on_submit=True):
            st.markdown("**➕ 添加新用户**")
            new_username = st.text_input("用户名", placeholder="唯一用户名")
            new_password = st.text_input("密码", type="password", placeholder="至少4位")
            new_role = st.selectbox("角色", ["操作员", "管理员"])
            new_display = st.text_input("显示名称", placeholder="如：张三")
            new_empid = st.text_input("工号", placeholder="员工编号")
            new_phone = st.text_input("联系电话", placeholder="手机号")
            if st.form_submit_button("✅ 创建用户", type="primary", use_container_width=True):
                if new_username and new_password and len(new_password) >= 4:
                    if add_user(new_username, new_password, new_role, new_display, new_empid, new_phone):
                        st.success(f"✅ 用户「{new_username}」创建成功！")
                        st.rerun()
                    else:
                        st.error("❌ 用户名已存在，请换一个")
                else:
                    st.warning("请填写完整信息，密码至少4位")

    st.divider()
    st.subheader("🔑 修改当前用户密码")
    with st.form("chg_self_pwd", clear_on_submit=True):
        cur_pwd = st.text_input("当前密码", type="password")
        new_self_pwd = st.text_input("新密码", type="password")
        confirm_pwd = st.text_input("确认新密码", type="password")
        if st.form_submit_button("💾 更新密码", type="primary"):
            current_user = st.session_state.get("logged_in_user", "")
            user_data = verify_user(current_user, cur_pwd)
            if not user_data:
                st.error("当前密码错误")
            elif new_self_pwd != confirm_pwd:
                st.error("两次密码不一致")
            elif len(new_self_pwd) < 4:
                st.warning("密码至少4位")
            else:
                conn = get_app_db()
                try:
                    conn.execute(
                        "UPDATE users SET password_hash = ? WHERE username = ?",
                        (hashlib.sha256(new_self_pwd.encode()).hexdigest(), current_user),
                    )
                    conn.commit()
                    st.success("✅ 密码已更新，下次请使用新密码登录")
                finally:
                    conn.close()
                st.rerun()
