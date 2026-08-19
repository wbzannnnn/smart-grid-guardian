import streamlit as st
import html
import json
import time
import traceback
import re
import os
import sqlite3
import hashlib
import io
import random
import threading
from datetime import datetime
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# PDF 导出依赖
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.embeddings import OpenAIEmbeddings
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
import pandas as pd
import numpy as np
from alarm_page import render_alarm_page
from app_shell import render_app_header, render_sidebar
from audit_history_page import render_audit_history_page
from home_page import render_home_page
from login_page import render_login_page
from operation_audit_page import render_operation_audit_page
from qa_page import render_qa_page
from ticket_page import render_ticket_page
from ui_helpers import inject_css_file, render_page_title
from knowledge_base_page import render_knowledge_base_page
from system_config_page import render_system_config_page
from stats_page import render_stats_page
from user_management_page import render_user_management_page

# ===========================================================
# ================= 🗄️ 应用级数据库（审计历史 + 用户体系）=================
# ===========================================================

# 临时使用脚本所在目录，后续会在下面重新赋值
_APP_DB_DIR = os.path.join(os.path.dirname(__file__), "data")
_APP_DB = os.path.join(_APP_DB_DIR, "app.db")


def _get_app_db():
    """获取应用数据库连接（线程安全）"""
    conn = sqlite3.connect(_APP_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_app_db():
    """初始化应用数据库表"""
    os.makedirs(_APP_DB_DIR, exist_ok=True)
    conn = _get_app_db()
    try:
        # 用户表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT '操作员',
                display_name TEXT,
                employee_id TEXT,
                phone TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                last_login TEXT
            )
        """)
        # 审核记录表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT UNIQUE NOT NULL,
                ticket_no TEXT,
                task_type TEXT,
                command TEXT NOT NULL,
                decision TEXT NOT NULL,
                risk_level TEXT,
                confidence INTEGER,
                violations TEXT,
                measures TEXT,
                auditor_text TEXT,
                red_text TEXT,
                blue_text TEXT,
                expert_text TEXT,
                decision_text TEXT,
                rag_context TEXT,
                operator TEXT NOT NULL,
                station_name TEXT,
                created_at TEXT NOT NULL
            )
        """)
        # 操作票表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operation_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_no TEXT UNIQUE NOT NULL,
                task_type TEXT,
                command TEXT,
                steps TEXT,
                status TEXT DEFAULT '草稿',
                created_by TEXT,
                station_name TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        # 告警表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alarms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alarm_id TEXT UNIQUE NOT NULL,
                alarm_type TEXT,
                level TEXT DEFAULT 'warning',
                title TEXT,
                content TEXT,
                source TEXT,
                status TEXT DEFAULT '待处理',
                operator TEXT,
                handler TEXT,
                handle_result TEXT,
                created_at TEXT,
                handled_at TEXT,
                ticket_no TEXT
            )
        """)
        conn.commit()

        # 创建默认管理员（密码：admin，hash后存储）
        existing = conn.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'").fetchone()[0]
        if existing == 0:
            pwd_hash = hashlib.sha256("admin".encode()).hexdigest()
            conn.execute(
                "INSERT INTO users (username, password_hash, role, display_name, created_at) VALUES (?, ?, ?, ?, ?)",
                ("admin", pwd_hash, "管理员", "系统管理员", datetime.now().isoformat())
            )
            conn.commit()

        # 创建默认操作员
        existing_op = conn.execute("SELECT COUNT(*) FROM users WHERE username = 'operator'").fetchone()[0]
        if existing_op == 0:
            pwd_hash = hashlib.sha256("operator".encode()).hexdigest()
            conn.execute(
                "INSERT INTO users (username, password_hash, role, display_name, created_at) VALUES (?, ?, ?, ?, ?)",
                ("operator", pwd_hash, "操作员", "值班操作员", datetime.now().isoformat())
            )
            conn.commit()
    finally:
        conn.close()


# 初始化数据库
_init_app_db()


# ===========================================================
# ================= 🔧 数据库 CRUD 操作函数 =================
# ===========================================================

def verify_user(username: str, password: str) -> Optional[Dict]:
    """验证用户登录，返回用户信息或 None"""
    conn = _get_app_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND password_hash = ? AND is_active = 1",
            (username, hashlib.sha256(password.encode()).hexdigest())
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def get_all_users() -> List[Dict]:
    """获取所有用户列表"""
    conn = _get_app_db()
    try:
        rows = conn.execute(
            "SELECT id, username, role, display_name, employee_id, phone, is_active, created_at, last_login FROM users ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_user(username: str, password: str, role: str, display_name: str, employee_id: str = "", phone: str = "") -> bool:
    """添加新用户"""
    conn = _get_app_db()
    try:
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        conn.execute(
            "INSERT INTO users (username, password_hash, role, display_name, employee_id, phone, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, pwd_hash, role, display_name, employee_id, phone, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_user_password(user_id: int, new_password: str):
    """更新用户密码"""
    conn = _get_app_db()
    try:
        pwd_hash = hashlib.sha256(new_password.encode()).hexdigest()
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))
        conn.commit()
    finally:
        conn.close()


def delete_user(user_id: int):
    """删除用户（软删除）"""
    conn = _get_app_db()
    try:
        conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def update_last_login(username: str):
    """更新用户最后登录时间"""
    conn = _get_app_db()
    try:
        conn.execute("UPDATE users SET last_login = ? WHERE username = ?", (datetime.now().isoformat(), username))
        conn.commit()
    finally:
        conn.close()


def _infer_audit_decision(record: Dict) -> str:
    """从新旧字段中归一化审核结论。"""
    direct = str(record.get("decision") or record.get("result") or "").strip().upper()
    if direct in ("ALLOW", "DENY"):
        return direct

    text = "\n".join(
        str(record.get(k) or "")
        for k in ("decision_text", "auditor_text", "red_text", "blue_text", "expert_text")
    )
    m = re.search(r"决策\s*[:：]\s*(ALLOW|DENY)\b", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    if re.search(r"\bALLOW\b", text, re.IGNORECASE) and not re.search(r"\bDENY\b", text, re.IGNORECASE):
        return "ALLOW"
    if re.search(r"\bDENY\b", text, re.IGNORECASE):
        return "DENY"
    if "调用失败" in text or "决策失败" in text:
        return "DENY"
    if "允许执行" in text and "拒绝执行" not in text:
        return "ALLOW"
    if "拒绝执行" in text or "退回修改" in text:
        return "DENY"
    return ""


def _infer_audit_created_at(record: Dict) -> str:
    """从新旧字段中归一化审核时间。"""
    created_at = str(record.get("created_at") or record.get("timestamp") or "").strip()
    if created_at:
        return created_at

    record_id = str(record.get("record_id") or "").strip()
    m = re.match(r"^[A-Z]?(\d{14})$", record_id)
    if not m:
        return ""
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M%S").isoformat()
    except ValueError:
        return ""


def _repair_audit_records():
    """修复旧版审核记录中缺失的 decision / created_at 字段。"""
    conn = _get_app_db()
    try:
        rows = conn.execute("""
            SELECT id, record_id, decision, created_at, decision_text, auditor_text, red_text, blue_text, expert_text
            FROM audit_records
            WHERE COALESCE(decision, '') = '' OR COALESCE(created_at, '') = ''
        """).fetchall()

        updated = False
        for row in rows:
            payload = dict(row)
            decision = _infer_audit_decision(payload)
            created_at = _infer_audit_created_at(payload)
            if not decision and not created_at:
                continue

            conn.execute(
                """
                UPDATE audit_records
                SET decision = CASE WHEN COALESCE(decision, '') = '' AND ? != '' THEN ? ELSE decision END,
                    created_at = CASE WHEN COALESCE(created_at, '') = '' AND ? != '' THEN ? ELSE created_at END
                WHERE id = ?
                """,
                (decision, decision, created_at, created_at, payload["id"]),
            )
            updated = True

        if updated:
            conn.commit()
    finally:
        conn.close()


def save_audit_record(record: Dict) -> str:
    """保存审核记录到数据库，返回 record_id"""
    decision = _infer_audit_decision(record)
    created_at = _infer_audit_created_at(record) or datetime.now().isoformat()
    conn = _get_app_db()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO audit_records
            (record_id, ticket_no, task_type, command, decision, risk_level, confidence,
             violations, measures, auditor_text, red_text, blue_text, expert_text,
             decision_text, rag_context, operator, station_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.get("record_id", ""),
            record.get("ticket_no", ""),
            record.get("task_type", ""),
            record.get("command", ""),
            decision,
            record.get("risk_level", ""),
            record.get("confidence", 0),
            record.get("violations", ""),
            record.get("measures", ""),
            record.get("auditor_text", ""),
            record.get("red_text", ""),
            record.get("blue_text", ""),
            record.get("expert_text", ""),
            record.get("decision_text", ""),
            record.get("rag_context", ""),
            record.get("operator", ""),
            record.get("station_name", ""),
            created_at,
        ))
        conn.commit()
        return record.get("record_id", "")
    finally:
        conn.close()


def get_audit_records(limit: int = 100, filter_decision: str = None, search_cmd: str = None) -> List[Dict]:
    """从数据库读取审核记录"""
    _repair_audit_records()
    conn = _get_app_db()
    try:
        query = "SELECT * FROM audit_records WHERE 1=1"
        params = []
        if filter_decision and filter_decision != "全部":
            query += " AND decision = ?"
            params.append(filter_decision)
        if search_cmd:
            query += " AND command LIKE ?"
            params.append(f"%{search_cmd}%")
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_audit_record_by_id(record_id: str) -> Optional[Dict]:
    """根据 record_id 获取单条审核记录"""
    conn = _get_app_db()
    try:
        row = conn.execute("SELECT * FROM audit_records WHERE record_id = ?", (record_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_audit_stats() -> Dict:
    """获取审核统计"""
    _repair_audit_records()
    conn = _get_app_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM audit_records").fetchone()[0]
        allow_cnt = conn.execute("SELECT COUNT(*) FROM audit_records WHERE decision = 'ALLOW'").fetchone()[0]
        deny_cnt = conn.execute("SELECT COUNT(*) FROM audit_records WHERE decision = 'DENY'").fetchone()[0]
        avg_conf = conn.execute("SELECT AVG(confidence) FROM audit_records").fetchone()[0] or 0
        today = datetime.now().strftime("%Y-%m-%d")
        today_cnt = conn.execute(
            "SELECT COUNT(*) FROM audit_records WHERE created_at LIKE ?", (f"{today}%",)
        ).fetchone()[0]
        return {
            "total": total,
            "allow": allow_cnt,
            "deny": deny_cnt,
            "avg_confidence": round(avg_conf, 1),
            "today": today_cnt,
        }
    finally:
        conn.close()


def save_operation_ticket(ticket: Dict) -> str:
    """保存操作票"""
    conn = _get_app_db()
    try:
        # 检查表结构
        cursor = conn.execute("PRAGMA table_info(operation_tickets)")
        columns = [col[1] for col in cursor.fetchall()]

        # 新增字段列表
        new_fields = [
            ("ticket_type", "TEXT DEFAULT '倒闸操作票'"),
            ("voltage_level", "TEXT DEFAULT '10kV'"),
            ("equipment_name", "TEXT DEFAULT ''"),
            ("equipment_no", "TEXT DEFAULT ''"),
            ("location", "TEXT DEFAULT ''"),
            ("current_status", "TEXT DEFAULT '运行'"),
            ("target_status", "TEXT DEFAULT '检修'"),
            ("hazard_analysis", "TEXT DEFAULT ''"),
            ("prevention_measures", "TEXT DEFAULT ''"),
            ("operator", "TEXT DEFAULT ''"),
            ("supervisor", "TEXT DEFAULT ''"),
            ("approver", "TEXT DEFAULT ''"),
        ]

        # 添加缺失的字段
        for field_name, field_def in new_fields:
            if field_name not in columns:
                try:
                    conn.execute(f"ALTER TABLE operation_tickets ADD COLUMN {field_name} {field_def}")
                except Exception:
                    pass

        conn.execute("""
            INSERT OR REPLACE INTO operation_tickets
            (ticket_no, ticket_type, task_type, voltage_level, equipment_name, equipment_no, location,
             current_status, target_status, command, hazard_analysis, prevention_measures,
             operator, supervisor, approver, steps, status, created_by, station_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticket.get("ticket_no", ""),
            ticket.get("ticket_type", "倒闸操作票"),
            ticket.get("task_type", ""),
            ticket.get("voltage_level", "10kV"),
            ticket.get("equipment_name", ""),
            ticket.get("equipment_no", ""),
            ticket.get("location", ""),
            ticket.get("current_status", "运行"),
            ticket.get("target_status", "检修"),
            ticket.get("command", ""),
            ticket.get("hazard_analysis", ""),
            ticket.get("prevention_measures", ""),
            ticket.get("operator", ""),
            ticket.get("supervisor", ""),
            ticket.get("approver", ""),
            ticket.get("steps", ""),
            ticket.get("status", "草稿"),
            ticket.get("created_by", ""),
            ticket.get("station_name", ""),
            ticket.get("created_at", ""),
            ticket.get("updated_at", ""),
        ))
        conn.commit()
        return ticket.get("ticket_no", "")
    finally:
        conn.close()


def get_operation_tickets(limit: int = 100) -> List[Dict]:
    """获取操作票列表"""
    conn = _get_app_db()
    try:
        rows = conn.execute(
            "SELECT * FROM operation_tickets ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ===========================================================
# ================= 告警管理功能 =================
# ===========================================================

def _get_alarms_db():
    """获取告警数据库连接"""
    return _get_app_db()


def save_alarm(alarm: Dict) -> str:
    """保存告警"""
    conn = _get_alarms_db()
    try:
        alarm_id = alarm.get("alarm_id") or f"AL{datetime.now().strftime('%Y%m%d%H%M%S')}"
        conn.execute("""
            INSERT OR REPLACE INTO alarms
            (alarm_id, alarm_type, level, title, content, source, status, operator, handler, handle_result, created_at, handled_at, ticket_no)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alarm_id,
            alarm.get("alarm_type", "系统告警"),
            alarm.get("level", "warning"),
            alarm.get("title", ""),
            alarm.get("content", ""),
            alarm.get("source", "系统"),
            alarm.get("status", "待处理"),
            alarm.get("operator", ""),
            alarm.get("handler", ""),
            alarm.get("handle_result", ""),
            alarm.get("created_at", datetime.now().isoformat()),
            alarm.get("handled_at", ""),
            alarm.get("ticket_no", ""),
        ))
        conn.commit()
        return alarm_id
    finally:
        conn.close()


def get_alarms(limit: int = 200, status: str = None, level: str = None) -> List[Dict]:
    """获取告警列表"""
    conn = _get_alarms_db()
    try:
        query = "SELECT * FROM alarms"
        params = []
        conditions = []
        if status and status != "全部":
            conditions.append("status = ?")
            params.append(status)
        if level and level != "全部":
            conditions.append("level = ?")
            params.append(level)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_alarm_status(alarm_id: str, status: str, handler: str = "", handle_result: str = "") -> bool:
    """更新告警状态"""
    conn = _get_alarms_db()
    try:
        handled_at = datetime.now().isoformat() if status in ("已处理", "已忽略") else ""
        conn.execute(
            "UPDATE alarms SET status = ?, handler = ?, handle_result = ?, handled_at = ? WHERE alarm_id = ?",
            (status, handler, handle_result, handled_at, alarm_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_alarm(alarm_id: str) -> bool:
    """删除告警"""
    conn = _get_alarms_db()
    try:
        conn.execute("DELETE FROM alarms WHERE alarm_id = ?", (alarm_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_alarm_stats() -> Dict:
    """获取告警统计"""
    conn = _get_alarms_db()
    try:
        rows = conn.execute("SELECT status, COUNT(*) as cnt FROM alarms GROUP BY status").fetchall()
        stats = {r[0]: r[1] for r in rows}
        total = sum(stats.values())

        rows_level = conn.execute("SELECT level, COUNT(*) as cnt FROM alarms GROUP BY level").fetchall()
        level_stats = {r[0]: r[1] for r in rows_level}

        rows_today = conn.execute(
            "SELECT COUNT(*) FROM alarms WHERE date(created_at) = date('now')"
        ).fetchone()[0]

        return {
            "total": total,
            "pending": stats.get("待处理", 0),
            "processing": stats.get("处理中", 0),
            "resolved": stats.get("已处理", 0),
            "ignored": stats.get("已忽略", 0),
            "critical": level_stats.get("critical", 0),
            "warning": level_stats.get("warning", 0),
            "info": level_stats.get("info", 0),
            "today": rows_today,
        }
    finally:
        conn.close()


def generate_alarm_from_audit(audit_record: Dict, risk_level: str) -> str:
    """从审核记录生成告警（高危审核自动生成告警）"""
    if risk_level not in ("HIGH", "MEDIUM"):
        return ""

    level_map = {"HIGH": "critical", "MEDIUM": "warning"}
    type_map = {"HIGH": "高危操作告警", "MEDIUM": "中危操作告警"}
    title_map = {"HIGH": "高危操作审核告警", "MEDIUM": "中危操作审核告警"}

    alarm = {
        "alarm_id": f"AL{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "alarm_type": type_map.get(risk_level, "操作告警"),
        "level": level_map.get(risk_level, "warning"),
        "title": title_map.get(risk_level, "操作告警"),
        "content": (
            f"操作指令：{audit_record.get('command', '')}\n"
            f"审核结果：{audit_record.get('result', '')}\n"
            f"风险等级：{risk_level}\n"
            f"违反规则：{audit_record.get('violations', '无')}\n"
            f"建议措施：{audit_record.get('measures', '无')}\n"
            f"操作员：{audit_record.get('operator', '')}\n"
            f"审核时间：{audit_record.get('timestamp', '')}"
        ),
        "source": "操作审核",
        "status": "待处理",
        "operator": audit_record.get("operator", ""),
        "ticket_no": audit_record.get("ticket_no", ""),
        "created_at": datetime.now().isoformat(),
    }
    return save_alarm(alarm)


# ===========================================================
# ================= PDF 导出功能 =================
# ===========================================================

def _register_chinese_font():
    """注册中文字体（Windows 环境）"""
    font_paths = [
        ("chinese", "C:/Windows/Fonts/msyh.ttc", "微软雅黑"),
        ("chinese", "C:/Windows/Fonts/simhei.ttf", "黑体"),
        ("chinese", "C:/Windows/Fonts/simsun.ttc", "宋体"),
    ]
    for name, path, _ in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                return name
            except Exception:
                pass
    return "Helvetica"


_CHINESE_FONT = _register_chinese_font() if _PDF_AVAILABLE else None


def _make_styles() -> Optional[Dict]:
    if not _PDF_AVAILABLE:
        return None
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", fontName=_CHINESE_FONT, fontSize=18, leading=24,
                                alignment=1, spaceAfter=10, textColor=colors.HexColor("#1a1a2e")),
        "subtitle": ParagraphStyle("subtitle", fontName=_CHINESE_FONT, fontSize=12, leading=16,
                                   alignment=1, spaceAfter=6, textColor=colors.HexColor("#555555")),
        "section": ParagraphStyle("section", fontName=_CHINESE_FONT, fontSize=13, leading=18,
                                  spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#1a1a2e"),
                                  borderPad=4),
        "body": ParagraphStyle("body", fontName=_CHINESE_FONT, fontSize=10, leading=16,
                                spaceAfter=4, textColor=colors.black),
        "warning": ParagraphStyle("warning", fontName=_CHINESE_FONT, fontSize=10, leading=14,
                                  textColor=colors.HexColor("#c62828")),
        "small": ParagraphStyle("small", fontName=_CHINESE_FONT, fontSize=8, leading=12,
                                textColor=colors.HexColor("#888888")),
        "table_header": ParagraphStyle("th", fontName=_CHINESE_FONT, fontSize=9, leading=12,
                                       textColor=colors.white, alignment=1),
        "table_cell": ParagraphStyle("td", fontName=_CHINESE_FONT, fontSize=9, leading=13,
                                      textColor=colors.black),
    }


def generate_audit_report_pdf(audit_data: Dict, results: Dict) -> bytes:
    """生成审核报告 PDF"""
    if not _PDF_AVAILABLE:
        raise RuntimeError("reportlab 未安装，无法生成 PDF")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = _make_styles()
    story = []

    # 标题
    story.append(Paragraph("变电站防误操作智能审核报告", styles["title"]))
    story.append(Paragraph("Substation Anti-Misoperation Intelligent Audit Report", styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#6B66CC")))
    story.append(Spacer(1, 8*mm))

    # 基本信息表
    dp = results.get("decision_parsed", {})
    decision = dp.get("decision", "DENY")
    risk = dp.get("risk_level", "MEDIUM")
    risk_color = {"HIGH": "#e53935", "MEDIUM": "#fb8c00", "LOW": "#43a047"}.get(risk, "#757575")

    info_data = [
        ["项目", "内容"],
        ["报告编号", audit_data.get("ticket_no", "")],
        ["操作指令", audit_data.get("user_command", audit_data.get("command", ""))],
        ["任务类型", audit_data.get("task_type", "")],
        ["审核时间", audit_data.get("timestamp", audit_data.get("created_at", ""))],
        ["操作员", audit_data.get("operator", audit_data.get("operator_name", ""))],
        ["电站名称", audit_data.get("station_name", "")],
        ["最终决策", "✅ 允许执行 (ALLOW)" if decision == "ALLOW" else "❌ 拒绝执行 (DENY)"],
        ["风险等级", dp.get("risk_level", "MEDIUM")],
        ["置信度", f"{dp.get('confidence', 80)}%"],
    ]
    t = Table(info_data, colWidths=[40*mm, 130*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6B66CC")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (_CHINESE_FONT,)*2),
        ("FONTSIZE", (9,)*2),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7ff")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))

    # 多智能体意见
    story.append(Paragraph("多智能体协同审核意见", styles["section"]))

    agents = [
        ("🔍 审核员意见", results.get("auditor", ""), colors.HexColor("#e8f5e9"), colors.HexColor("#2e7d32")),
        ("🥷 红队攻击分析", results.get("red", ""), colors.HexColor("#ffebee"), colors.HexColor("#c62828")),
        ("🛡️ 蓝队防御分析", results.get("blue", ""), colors.HexColor("#e3f2fd"), colors.HexColor("#1565c0")),
        ("📚 规程专家意见", results.get("expert", ""), colors.HexColor("#fff8e1"), colors.HexColor("#e65100")),
    ]
    for name, content, bg, tc in agents:
        story.append(Paragraph(f"<b>{name}</b>", ParagraphStyle("agent_h", fontName=_CHINESE_FONT,
                                                                   fontSize=10, leading=14,
                                                                   textColor=tc, spaceAfter=2)))
        story.append(Paragraph((content or "（无）").replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 3*mm))

    # 违规和建议
    story.append(Paragraph("合规性判定", styles["section"]))
    violations = dp.get("violations", "无")
    measures = dp.get("measures", "无")
    decision_txt = results.get("decision", "")

    story.append(Paragraph(f"<b>违反规则：</b>{violations}", styles["body"]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(f"<b>整改建议：</b>{measures}", styles["body"]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(f"<b>决策理由：</b>{decision_txt}", styles["body"]))

    # 高危警告
    if risk == "HIGH" or decision == "DENY":
        story.append(Spacer(1, 4*mm))
        warn_data = [["⚠️ 高危/拒绝操作，请严格执行操作票与监护制度，经主管领导审批后方可执行。"]]
        wt = Table(warn_data, colWidths=[170*mm])
        wt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffebee")),
            ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#e53935")),
            ("FONTNAME", (_CHINESE_FONT,)),
            ("FONTSIZE", (9,)),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(wt)

    # 页脚
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Paragraph(
        f"本报告由智电卫士变电站防误操作智能审核系统自动生成 | 版本 {APP_VERSION} | "
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        styles["small"]
    ))

    doc.build(story)
    return buf.getvalue()


def generate_operation_ticket_pdf(ticket_data: Dict) -> bytes:
    """生成操作票 PDF"""
    if not _PDF_AVAILABLE:
        raise RuntimeError("reportlab 未安装，无法生成 PDF")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = _make_styles()
    story = []

    story.append(Paragraph("电气操作票", styles["title"]))
    story.append(Paragraph(f"编号：{ticket_data.get('ticket_no', '')}", styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#6B66CC")))
    story.append(Spacer(1, 6*mm))

    # 操作票信息
    info_data = [
        ["项目", "内容"],
        ["操作票类型", ticket_data.get("ticket_type", "倒闸操作票")],
        ["变电站", ticket_data.get("station_name", "")],
        ["电压等级", ticket_data.get("voltage_level", "")],
        ["操作设备", f"{ticket_data.get('equipment_name', '')} ({ticket_data.get('equipment_no', '')})"],
        ["设备位置", ticket_data.get("location", "")],
        ["操作前状态", ticket_data.get("current_status", "")],
        ["操作后状态", ticket_data.get("target_status", "")],
        ["操作任务", ticket_data.get("command", "")],
        ["任务类型", ticket_data.get("task_type", "")],
        ["危险点分析", ticket_data.get("hazard_analysis", "（见预控措施）")],
        ["预控措施", ticket_data.get("prevention_measures", "（见操作步骤）")],
    ]
    t = Table(info_data, colWidths=[35*mm, 135*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6B66CC")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (_CHINESE_FONT,)*2),
        ("FONTSIZE", (9,)*2),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7ff")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 8*mm))

    # 人员签字
    sig_data = [
        ["操作人", "监护人", "值班负责人"],
        [ticket_data.get("operator", "（签字）"), ticket_data.get("supervisor", "（签字）"), ticket_data.get("approver", "（签字）")],
        ["日期：___________", "日期：___________", "日期：___________"],
    ]
    t_sig = Table(sig_data, colWidths=[56*mm, 56*mm, 56*mm])
    t_sig.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#8b5cf6")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (_CHINESE_FONT,)*3),
        ("FONTSIZE", (10,)*3),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(t_sig)
    story.append(Spacer(1, 8*mm))

    # 操作步骤
    story.append(Paragraph("操作步骤", styles["section"]))
    steps_str = ticket_data.get("steps", "")
    if steps_str:
        try:
            steps = json.loads(steps_str)
        except Exception:
            steps = [s.strip() for s in steps_str.split("\n") if s.strip()]
    else:
        steps = ["（无操作步骤，请生成后填写）"]

    step_data = [["序号", "操作步骤", "操作人", "时间", "确认"]]
    for i, s in enumerate(steps, 1):
        if isinstance(s, dict):
            op_text = s.get("operation", str(s))
        else:
            op_text = str(s)
        step_data.append([str(i), op_text, "（签字）", "", "（确认）"])

    t2 = Table(step_data, colWidths=[12*mm, 90*mm, 25*mm, 25*mm, 25*mm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (_CHINESE_FONT,)*5),
        ("FONTSIZE", (9,)*5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7ff")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t2)

    # 安全注意事项
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("安全注意事项（依据GB 26860-2011）", styles["section"]))
    story.append(Paragraph(
        "1. 操作前必须核对设备名称、编号和位置<br/>"
        "2. 严格执行监护制度，必须由两人执行，一人操作，一人监护<br/>"
        "3. 重要操作由站长或值班长监护<br/>"
        "4. 操作中发现异常立即停止并报告值班负责人<br/>"
        "5. 每项操作后应检查设备状态",
        styles["body"]
    ))

    # 页脚
    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Paragraph(
        f"智电卫士变电站防误操作智能审核系统 | 版本 {APP_VERSION} | "
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        styles["small"]
    ))

    doc.build(story)
    return buf.getvalue()


# ===========================================================
# ================= 📚 RAG 知识库（numpy 向量引擎 + 深度语义Embedding）=================
# ===========================================================

_KNOWLEDGE_BASE_DIR = os.path.join(os.path.dirname(__file__), "data")
_KNOWLEDGE_DB = os.path.join(_KNOWLEDGE_BASE_DIR, "knowledge.db")
_INDEX_FILE = os.path.join(_KNOWLEDGE_BASE_DIR, "vector_index.npz")
_LLM_INDEX_FILE = os.path.join(_KNOWLEDGE_BASE_DIR, "llm_vector_index.npz")
_DOC_FILE = os.path.join(_KNOWLEDGE_BASE_DIR, "documents.json")

# 更新应用数据库路径（与知识库共用 data 目录）
_APP_DB_DIR = _KNOWLEDGE_BASE_DIR
_APP_DB = os.path.join(_APP_DB_DIR, "app.db")

_EMBED_DIM = 1536  # OpenAI text-embedding-ada-002 / text-embedding-3-small

# ---------- 内置规程数据（8类） ----------
BUILTIN_DOCS = [
    {"id": "r001", "category": "通用安全规程", "title": "变电站通用安全规程",
     "content": "所有操作人员必须持有有效的工作票和操作票。操作前应核对设备名称、编号和位置，确认无误后方可操作。操作过程中应使用合格的安全工器具，严格执行监护制度，重要操作由站长或值班长监护。"},
    {"id": "r002", "category": "通用安全规程", "title": "验电操作规程",
     "content": "验电时，应使用相应电压等级且合格的验电器。验电前应先在有电设备上试验验电器完好。验电应逐相进行，对断开位置的设备验电时，对进出线各相均应验明。禁止以设备分合位置指示灯、信号灯、仪表等作为无电依据。"},
    {"id": "r003", "category": "通用安全规程", "title": "挂接地线操作规程",
     "content": "挂接地线前必须先验明设备确无电压。接地线应使用多股软铜线，截面不小于25mm²。挂接地线时应先接接地端，再接设备端，拆除时顺序相反。禁止使用缠绕方式接地。禁止在雷雨天进行室外直接验电和挂接地线操作。"},
    {"id": "r004", "category": "通用安全规程", "title": "操作票填写规范",
     "content": "操作票应使用统一格式，逐项填写操作任务和步骤，不得漏项、倒项。每项操作应填写设备双重名称（设备名称和编号）。操作票填写后应由监护人和值班负责人审核签名。操作中发生疑问应立即停止操作并报告值班负责人。"},
    {"id": "r005", "category": "五防规则", "title": "五防规则一：防止误分、误合断路器",
     "content": "断路器操作必须使用操作票，并严格按操作票步骤执行。操作前必须核对设备名称、编号和运行状态。严禁无票操作、随意操作。非运行人员操作断路器时应有运行人员监护。"},
    {"id": "r006", "category": "五防规则", "title": "五防规则二：防止带负荷拉、合隔离开关",
     "content": "隔离开关只能用来接通或断开无负荷或小负荷电路。操作前必须确认回路中无负荷，检查负荷电流指示为零或接近零方可操作。严禁带负荷拉、合隔离开关，发现带负荷拉、合隔离开关时应立即停止并汇报。"},
    {"id": "r007", "category": "五防规则", "title": "五防规则三：防止带电挂接地线（含接地刀闸）",
     "content": "挂接地线前必须验明设备确无电压，确认停电范围和设备状态后方可操作。接地线应使用多股软铜线，接地端和设备端均应可靠连接。严禁在雷雨天气进行室外验电和挂接地线操作。"},
    {"id": "r008", "category": "五防规则", "title": "五防规则四：防止带接地线（接地刀闸）合断路器（隔离开关）",
     "content": "设备送电前必须确认接地线或接地刀闸已全部拆除，检查各侧确无接地短路。拆除接地线应先拆设备端再拆接地端，并做好记录。合闸操作前必须进行五防校验和设备状态确认。"},
    {"id": "r009", "category": "五防规则", "title": "五防规则五：防止误入带电间隔",
     "content": "巡视或操作时必须确认设备间隔状态，严禁擅自进入带电间隔。检修设备与带电设备之间应装设临时遮栏，并悬挂警示标志。工作负责人应向工作人员明确交代带电范围和安全注意事项。"},
    {"id": "r010", "category": "倒闸操作", "title": "线路停送电操作规程",
     "content": "线路停电操作：先断开线路断路器，确认负荷电流为零后，先拉线路侧隔离开关，再拉母线侧隔achen关。线路送电操作：先合母线侧隔离开关，再合线路侧隔离开关，最后合断路器。"},
    {"id": "r011", "category": "倒闸操作", "title": "主变停送电操作规程",
     "content": "主变停电：先断开低压侧断路器，再断开中压侧断路器，最后断开高压侧断路器，然后按顺序拉开各侧隔离开关。主变送电：先合高压侧隔离开关，再合中压侧，最后合低压侧断路器，变压器充电后检查声音和温度。"},
    {"id": "r012", "category": "倒闸操作", "title": "母线倒闸操作规程",
     "content": "母线倒闸操作必须使用操作票，在副值班或值班负责人监护下进行。倒闸前应先将备用母线充电，确保备用母线正常。倒闸时注意防止继电保护误动作，必要时申请调度退出自动装置。"},
]

# ---------- 简单文本嵌入（用词袋近似，无 API 调用） ----------
def _simple_embed(texts: List[str]) -> np.ndarray:
    """使用 TF-IDF 风格词袋生成伪嵌入向量（用于本地无 API 场景）"""
    import re as _re
    all_words = set()
    for t in texts:
        words = _re.findall(r'[\u4e00-\u9fff_a-zA-Z0-9]{2,}', t.lower())
        all_words.update(words)
    vocab = {w: i for i, w in enumerate(sorted(all_words))}
    dim = max(len(vocab), _EMBED_DIM)
    vectors = np.zeros((len(texts), dim), dtype=np.float32)
    for i, t in enumerate(texts):
        words = _re.findall(r'[\u4e00-\u9fff_a-zA-Z0-9]{2,}', t.lower())
        freq = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        total = max(len(words), 1)
        for w, c in freq.items():
            if w in vocab:
                vectors[i, vocab[w]] = c / total
    if len(vocab) < _EMBED_DIM:
        extra = np.random.randn(len(texts), _EMBED_DIM - len(vocab)).astype(np.float32) * 0.01
        vectors = np.concatenate([vectors, extra], axis=1)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vectors / norms


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """行归一化后的余弦相似度"""
    return np.dot(a, b.T)


class KnowledgeBase:
    """轻量级知识库：SQLite 存储元数据 + TF-IDF 向量索引 + LLM 向量索引（双索引）"""

    def __init__(self, api_key: str, base_url: str):
        os.makedirs(_KNOWLEDGE_BASE_DIR, exist_ok=True)
        self.api_key = api_key
        self.base_url = base_url
        self._conn = sqlite3.connect(_KNOWLEDGE_DB, check_same_thread=False)
        self._init_db()
        self._embedder = None
        self._vectors = None      # TF-IDF 向量索引
        self._llm_vectors = None  # LLM 深度语义向量索引
        self._docs = []
        self._llm_built = False
        self._load_index()

    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS docs (
                id TEXT PRIMARY KEY,
                category TEXT,
                title TEXT,
                content TEXT,
                source TEXT DEFAULT 'builtin',
                created_at TEXT
            )
        """)
        # 初始化内置规程
        existing = self._conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        if existing == 0:
            for doc in BUILTIN_DOCS:
                self._conn.execute(
                    "INSERT OR IGNORE INTO docs VALUES (?, ?, ?, ?, 'builtin', ?)",
                    (doc["id"], doc["category"], doc["title"], doc["content"], datetime.now().isoformat())
                )
            self._conn.commit()
        self._conn.commit()

    def _load_index(self):
        # 加载 TF-IDF 索引
        if os.path.exists(_INDEX_FILE) and os.path.exists(_DOC_FILE):
            data = np.load(_INDEX_FILE, allow_pickle=True)
            self._vectors = data["vectors"]
            with open(_DOC_FILE, "r", encoding="utf-8") as f:
                self._docs = json.load(f)
        # 加载 LLM 向量索引
        if os.path.exists(_LLM_INDEX_FILE):
            data = np.load(_LLM_INDEX_FILE, allow_pickle=True)
            self._llm_vectors = data["vectors"]
            self._llm_built = True

    def _build_index(self):
        rows = self._conn.execute(
            "SELECT id, category, title, content FROM docs"
        ).fetchall()
        self._docs = [{"id": r[0], "category": r[1], "title": r[2], "content": r[3]} for r in rows]
        if not self._docs:
            self._vectors = np.empty((0, _EMBED_DIM), dtype=np.float32)
            self._llm_vectors = np.empty((0, _EMBED_DIM), dtype=np.float32)
            return
        # TF-IDF 索引
        texts = [f"{d['title']}。{d['content']}" for d in self._docs]
        self._vectors = _simple_embed(texts)
        np.savez(_INDEX_FILE, vectors=self._vectors)
        with open(_DOC_FILE, "w", encoding="utf-8") as f:
            json.dump(self._docs, f, ensure_ascii=False)

    def _build_llm_index(self, force: bool = False):
        """构建 LLM 深度语义向量索引（默认自动构建）"""
        if self._llm_built and not force and self._llm_vectors is not None:
            return
        if not self._docs:
            return
        ed = self._get_embedder()
        if not ed:
            return
        try:
            texts = [f"{d['title']}。{d['content']}" for d in self._docs]
            embeddings = ed.embed_documents(texts)
            self._llm_vectors = np.array(embeddings, dtype=np.float32)
            # L2 归一化
            norms = np.linalg.norm(self._llm_vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1
            self._llm_vectors = self._llm_vectors / norms
            np.savez(_LLM_INDEX_FILE, vectors=self._llm_vectors)
            self._llm_built = True
        except Exception as ex:
            import logging as _log
            _log.warning(f"[RAG] LLM 向量索引构建失败，将降级使用 TF-IDF：{ex}")
            self._llm_built = False

    def _get_embedder(self):
        if self._embedder is None:
            try:
                self._embedder = OpenAIEmbeddings(
                    model="text-embedding-3-small",
                    openai_api_key=self.api_key,
                    openai_api_base=self.base_url,
                    timeout=30,
                )
            except Exception:
                self._embedder = None
        return self._embedder

    def search(self, query: str, top_k: int = 5, use_llm_embed: bool = True) -> List[Dict]:
        """检索最相关的规程片段，默认使用 LLM 深度语义检索"""
        if not self._docs:
            return []

        # 默认启用 LLM 深度语义检索（自动构建索引）
        if use_llm_embed:
            self._build_llm_index()
            if self._llm_vectors is not None and len(self._llm_vectors) == len(self._docs):
                try:
                    ed = self._get_embedder()
                    if ed:
                        qv = np.array(ed.embed_query(query), dtype=np.float32)
                        qv = qv / (np.linalg.norm(qv) + 1e-9)
                        sims = np.dot(self._llm_vectors, qv)
                        top_idx = np.argsort(sims)[::-1][:top_k]
                        return [{**self._docs[i], "score": float(sims[i])} for i in top_idx if sims[i] > 0.05]
                except Exception:
                    pass

        # 降级到 TF-IDF
        query_v = _simple_embed([query])[0]
        sims = _cosine_sim(query_v.reshape(1, -1), self._vectors)[0]
        top_idx = np.argsort(sims)[::-1][:top_k]
        results = []
        for idx in top_idx:
            if sims[idx] > 0.05:
                results.append({**self._docs[idx], "score": float(sims[idx])})
        return results

    def add_doc(self, category: str, title: str, content: str) -> str:
        doc_id = f"u{datetime.now().strftime('%Y%m%d%H%M%S')}{np.random.randint(100, 999)}"
        self._conn.execute(
            "INSERT INTO docs VALUES (?, ?, ?, ?, 'user', ?)",
            (doc_id, category, title, content, datetime.now().isoformat())
        )
        self._conn.commit()
        self._build_index()
        self._llm_built = False
        return doc_id

    def delete_doc(self, doc_id: str):
        self._conn.execute("DELETE FROM docs WHERE id = ?", (doc_id,))
        self._conn.commit()
        self._build_index()
        self._llm_built = False

    def list_docs(self) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT id, category, title, content, source, created_at FROM docs ORDER BY created_at DESC"
        ).fetchall()
        return [{"id": r[0], "category": r[1], "title": r[2], "content": r[3], "source": r[4], "created_at": r[5]} for r in rows]

    def get_stats(self) -> Dict:
        total = self._conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        by_cat = dict(self._conn.execute(
            "SELECT category, COUNT(*) FROM docs GROUP BY category"
        ).fetchall())
        by_src = dict(self._conn.execute(
            "SELECT source, COUNT(*) FROM docs GROUP BY source"
        ).fetchall())
        return {"total": total, "by_category": by_cat, "by_source": by_src}


# ===========================================================
# ================= 🛠️ Agent Tool 系统（LangChain Tool）=================
# ===========================================================
from langchain_core.tools import tool

@tool
def search_regulations(query: str) -> str:
    """搜索安全规程和五防规则。当需要查询相关规程条款、操作规范、规则依据时使用此工具。
    输入：搜索关键词，如"验电操作"、"带负荷拉隔离开关"、"接地线操作"等。
    返回：最相关的规程条文列表，包含规程类别、标题、内容和相似度得分。
    """
    return _search_regulations_impl(query)


def _search_regulations_impl(query: str, use_llm_embed: bool = False) -> str:
    try:
        kb = _get_kb()
        results = kb.search(query, top_k=2, use_llm_embed=use_llm_embed)
        if not results:
            return "未找到相关规程。"
        lines = []
        for i, r in enumerate(results, 1):
            content = str(r["content"]).replace("\n", " ").strip()[:140]
            lines.append(f"[{i}]【{r['category']}】{r['title']}：{content}")
        return "\n".join(lines)
    except Exception as e:
        return f"规程检索失败：{str(e)}"

def _check_five_preventions_impl(command: str) -> Dict:
    command = str(command or "")
    violations = []
    checks = [
        ("防止误分、误合断路器", "断路器" in command and ("误分" in command or "误合" in command or "无票" in command or "随意" in command)),
        ("防止带负荷拉/合隔离开关", "隔离开关" in command and ("负荷" in command or "电流" in command)),
        ("防止带电挂接地线", "接地" in command and ("带电" in command or "未验电" in command)),
        ("防止带接地线合断路器", ("接地" in command or "地线" in command) and "合" in command),
        ("防止误入带电间隔", "间隔" in command and ("误入" in command or "未确认" in command)),
    ]
    for rule, violated in checks:
        if violated:
            violations.append(f"⚠️ 可能违反：{rule}")
    return {
        "ok": not violations,
        "violations": violations,
    }


def _format_five_preventions_result(command: str) -> str:
    result = _check_five_preventions_impl(command)
    if result["violations"]:
        return "五防校验结果：\n" + "\n".join(result["violations"])
    return "五防校验结果：✅ 未检测到明显违反五防规则的情况，但应以实际设备状态和操作票为准。"


@tool
def check_five_preventions(command: str) -> str:
    """五防规则校验工具。检查操作指令是否违反五防规则（防止误分/误合断路器、防止带负荷拉/合隔离开关、防止带电挂接地线、防止带接地线合断路器、防止误入带电间隔）。
    输入：完整的操作指令文字。
    返回：逐项五防规则校验结果，标注是否违反。
    """
    return _format_five_preventions_result(command)

@tool
def analyze_topology(command: str) -> str:
    """拓扑分析工具。分析操作指令涉及的设备、回路及相互关系，返回拓扑结构描述。
    输入：操作指令。
    返回：设备关系图描述、涉及的一次设备清单及状态。
    """
    return _analyze_topology_impl(command)


def _analyze_topology_impl(command: str) -> str:
    devices = []
    if "线路" in command or "断路器" in command or "隔离开关" in command:
        devices.append("断路器（Q F）")
        devices.append("线路隔离开关")
        devices.append("母线隔离开关")
    if "主变" in command or "变压器" in command:
        devices.append("主变压器")
        devices.append("高/中/低压侧断路器")
    if "母线" in command:
        devices.append("母线")
        devices.append("母线隔离开关")
    if "接地" in command:
        devices.append("接地刀闸/接地线")
    if not devices:
        devices = ["断路器", "隔离开关", "母线", "接地装置"]
    return (
        "拓扑分析结果：\n"
        f"涉及设备：{'、'.join(set(devices))}\n"
        "设备关系：按典型变电站单母线或双母线结构，操作需严格按顺序执行。\n"
        "建议操作顺序：断开断路器 → 拉开隔离开关 → 验电 → 挂接地线。"
    )


_SCADA_CACHE_LOCK = threading.Lock()
_ACTIVE_SCADA_CONTEXT = {
    "audit_id": None,
    "command": "",
    "task_type": "",
    "snapshot": {},
}


def _normalize_scada_device_key(device: str) -> str:
    text = re.sub(r"\s+", "", str(device or ""))
    if not text:
        return "UNKNOWN"
    ids = re.findall(r"[A-Za-z]*\d+[A-Za-z]*", text)
    if ids:
        return ids[0].upper()
    if "主变" in text or "变压器" in text:
        return "主变"
    if "母线" in text:
        return "母线"
    if "线路" in text:
        return "线路"
    if "断路器" in text:
        return "断路器"
    if "隔离开关" in text:
        return "隔离开关"
    return text[:20]


def _set_active_scada_context(audit_id: str, command: str, task_type: str) -> None:
    with _SCADA_CACHE_LOCK:
        _ACTIVE_SCADA_CONTEXT["audit_id"] = audit_id
        _ACTIVE_SCADA_CONTEXT["command"] = command or ""
        _ACTIVE_SCADA_CONTEXT["task_type"] = task_type or ""
        _ACTIVE_SCADA_CONTEXT["snapshot"] = {}


def _clear_active_scada_context(audit_id: Optional[str] = None) -> None:
    with _SCADA_CACHE_LOCK:
        if audit_id and _ACTIVE_SCADA_CONTEXT.get("audit_id") != audit_id:
            return
        _ACTIVE_SCADA_CONTEXT["audit_id"] = None
        _ACTIVE_SCADA_CONTEXT["command"] = ""
        _ACTIVE_SCADA_CONTEXT["task_type"] = ""
        _ACTIVE_SCADA_CONTEXT["snapshot"] = {}


def _build_scada_snapshot(device: str) -> str:
    with _SCADA_CACHE_LOCK:
        audit_id = _ACTIVE_SCADA_CONTEXT.get("audit_id") or "default"
        command = _ACTIVE_SCADA_CONTEXT.get("command", "")
        task_type = _ACTIVE_SCADA_CONTEXT.get("task_type", "")

    norm_key = _normalize_scada_device_key(device)
    seed_src = f"{audit_id}|{norm_key}|{task_type}"
    seed = int(hashlib.sha256(seed_src.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)

    combined = f"{task_type} {command}"
    if any(k in combined for k in ["停电", "转检修", "转冷备用", "退出运行"]):
        preferred_status = "运行中"
    elif any(k in combined for k in ["送电", "恢复运行", "恢复送电", "投入"]):
        preferred_status = "冷备用"
    else:
        preferred_status = None

    statuses = ["运行中", "热备用", "冷备用", "检修中"]
    states = ["正常", "轻载", "重载", "告警"]
    status = preferred_status or rng.choice(statuses)
    state = "正常" if preferred_status else rng.choice(states)

    if "主变" in device or "变压器" in device:
        load = rng.randint(45, 78) if preferred_status == "运行中" else rng.randint(0, 35)
        temp = rng.randint(48, 66) if preferred_status == "运行中" else rng.randint(28, 45)
        return f"设备：{device}\n运行状态：{status}\n负载率：{load}%\n油温：{temp}℃\n状态：{state}"
    if "母线" in device:
        volt = round(rng.uniform(219.0, 225.0), 1) if preferred_status == "运行中" else round(rng.uniform(0.0, 5.0), 1)
        return f"设备：{device}\n运行状态：{status}\n电压：{volt}kV\n状态：{state}"

    current = round(rng.uniform(65.0, 120.0), 1) if preferred_status == "运行中" else round(rng.uniform(0.0, 12.0), 1)
    return f"设备：{device}\n运行状态：{status}\n电流：{current}A\n状态：{state}"


@tool
def query_scada_status(device: str) -> str:
    """SCADA 数据查询工具。查询指定设备的实时运行状态、负载情况。
    输入：设备名称或编号。
    返回：设备当前运行状态、负载率、相关参数。
    """
    return _query_scada_status_impl(device)


def _query_scada_status_impl(device: str) -> str:
    norm_key = _normalize_scada_device_key(device)
    with _SCADA_CACHE_LOCK:
        snapshot = _ACTIVE_SCADA_CONTEXT.setdefault("snapshot", {})
        if norm_key not in snapshot:
            snapshot[norm_key] = _build_scada_snapshot(device)
        return snapshot[norm_key]

def _validate_operation_compliance_impl(command: str) -> Dict:
    command = str(command or "")
    issues = []
    if not command or len(command.strip()) < 4:
        issues.append("⚠️ 操作指令不完整或为空")
    if "无票" in command or ("直接" in command and "操作" in command):
        issues.append("⚠️ 违反操作票制度：操作必须凭票执行")
    if "接地" in command and "验电" not in command and "验明" not in command:
        issues.append("⚠️ 违反接地操作规程：挂接地线前必须先验明无电")
    if "负荷" in command and "隔离开关" in command:
        issues.append("⚠️ 严重违规：严禁带负荷拉、合隔离开关")
    if "合" in command and "接地" in command:
        issues.append("⚠️ 违反送电规程：送电前必须确认接地装置已拆除")
    return {
        "ok": not issues,
        "issues": issues,
    }


def _format_operation_compliance_result(command: str) -> str:
    result = _validate_operation_compliance_impl(command)
    if not result["issues"]:
        return "合规性判定：✅ 未发现明显违规项。建议严格执行操作票制度和监护制度。"
    return "合规性判定：\n" + "\n".join(result["issues"]) + "\n\n请严格按规程执行操作。"


@tool
def validate_operation_compliance(command: str) -> str:
    """操作合规性验证工具。综合规程、五防、设备状态判断操作是否合规，返回具体违规条款和改进建议。
    输入：完整操作指令。
    返回：合规性判定及整改建议列表。
    """
    return _format_operation_compliance_result(command)


def _find_next_keyword(text: str, keywords: List[str], start: int = 0) -> int:
    hits = []
    for keyword in keywords:
        idx = text.find(keyword, start)
        if idx >= 0:
            hits.append(idx)
    return min(hits) if hits else -1


def _is_standard_line_outage_sequence(command: str, task_type: str = "") -> bool:
    text = re.sub(r"\s+", "", str(command or ""))
    scene = f"{task_type}{text}"
    if "线路" not in scene:
        return False
    if not any(flag in scene for flag in ("停电", "冷备用", "退出运行")):
        return False

    breaker_idx = _find_next_keyword(text, ["断路器", "开关柜断路器"])
    line_iso_idx = _find_next_keyword(text, ["线路侧隔离开关", "线路侧刀闸", "线路侧隔离刀闸"], breaker_idx + 1 if breaker_idx >= 0 else 0)
    bus_iso_idx = _find_next_keyword(text, ["母线侧隔离开关", "母线侧刀闸", "母线侧隔离刀闸"], line_iso_idx + 1 if line_iso_idx >= 0 else 0)
    return breaker_idx >= 0 and line_iso_idx > breaker_idx and bus_iso_idx > line_iso_idx


def _build_rule_based_audit_summary(command: str, task_type: str = "") -> Dict:
    five = _check_five_preventions_impl(command)
    compliance = _validate_operation_compliance_impl(command)
    matched_patterns = []
    if _is_standard_line_outage_sequence(command, task_type):
        matched_patterns.append("线路停电顺序符合“先断断路器→再拉线路侧→最后拉母线侧”")

    safe_to_allow = five["ok"] and compliance["ok"] and bool(matched_patterns)
    return {
        "five_preventions_ok": five["ok"],
        "five_preventions_violations": five["violations"],
        "compliance_ok": compliance["ok"],
        "compliance_issues": compliance["issues"],
        "matched_patterns": matched_patterns,
        "safe_to_allow": safe_to_allow,
    }

def _get_kb():
    """获取当前 session 的知识库实例（懒加载）"""
    if "kb_instance" not in st.session_state:
        api_key = st.session_state.get("api_key") or DEEPSEEK_API_KEY
        st.session_state.kb_instance = KnowledgeBase(api_key, DEEPSEEK_BASE_URL)
    return st.session_state.kb_instance


# ===========================================================
# ================= 配置区域 =================
def _read_secret(name: str, default: str = "") -> str:
    """Read deployment secrets without storing them in source control."""
    value = os.getenv(name, default)
    try:
        value = st.secrets.get(name, value)
    except Exception:
        pass
    return str(value or "").strip()


DEEPSEEK_BASE_URL = _read_secret("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL_NAME = _read_secret("MODEL_NAME", "deepseek-v4-pro")
DEEPSEEK_THINKING = _read_secret("DEEPSEEK_THINKING", "disabled").lower()
LLM_FINAL_DECISION = _read_secret("LLM_FINAL_DECISION", "false").lower() in {"true", "1", "yes", "on"}
DEEPSEEK_API_KEY = _read_secret("DEEPSEEK_API_KEY")

# 演示登录（可按需修改）
LOGIN_DEMO_USER = "admin"
LOGIN_DEMO_PASS = "admin"

# SCADA 系统配置
SCADA_CONFIG = {
    'enabled': False,
    'type': 'mock',
    'api_url': 'http://localhost:8080/api/scada',
    'refresh_interval': 60,
}

# ===========================================================
st.set_page_config(
    page_title="智电卫士 | 变电站防误操作智能审核系统",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# ================= 🎨 自定义 CSS =================
inject_css_file("assets/styles.css")

# ================= 📊 初始化 Session State =================
if 'audit_history' not in st.session_state:
    st.session_state.audit_history = []
if 'data_source_configured' not in st.session_state:
    st.session_state.data_source_configured = False
if 'api_configured' not in st.session_state:
    st.session_state.api_configured = False
if 'llm_client' not in st.session_state:
    st.session_state.llm_client = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'home'
if 'last_audit_full' not in st.session_state:
    st.session_state.last_audit_full = None
if 'logged_in_user' not in st.session_state:
    st.session_state.logged_in_user = 'admin'
if 'user_role' not in st.session_state:
    st.session_state.user_role = '管理员'
if 'display_name' not in st.session_state:
    st.session_state.display_name = '系统管理员'

APP_VERSION = 'v2.1.0'
LAST_UPDATE = '2026-03-29'

def _risk_label_and_color(risk: str):
    return {
        'HIGH': ('高危', '#e53935'),
        'MEDIUM': ('中危', '#fb8c00'),
        'LOW': ('低危', '#43a047'),
    }.get(risk.upper(), ('未知', '#757575'))

def render_audit_result_view(la: Dict):
    results = la['results']
    dp = results['decision_parsed']
    decision = dp['decision']
    risk = dp['risk_level']
    task_type = la['task_type']
    user_command = la['user_command']
    ticket_no = la['ticket_no']
    ts = la['timestamp']
    station = st.session_state.get('station_name') or '一号电站'
    operator = st.session_state.get('username') or st.session_state.get('logged_in_user', 'admin')
    st.success('✅ 审核完成！')
    r_cn, r_col = _risk_label_and_color(risk)
    dec_html = '拒绝执行' if decision == 'DENY' else '允许执行'
    fin_cls = 'fin-deny' if decision == 'DENY' else 'fin-allow'
    lc, rc = st.columns([1, 1])
    
    # 格式化文本，去除 Markdown 标记但保留结构
    def fmt_text(t):
        if not t:
            return '（暂无）'
        t = t.replace('**', '').replace('*', '').replace('##', '').replace('#', '').strip()
        return t
    
    with lc:
        st.markdown('### ⚡ 最终审核决策')
        st.markdown(f'<div class="fin-box {fin_cls}">{dec_html}（模型结论: {decision}）</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="risk-badge">
            <div class="risk-circle" style="background:{r_col};">{r_cn}</div>
            <div style="font-size:0.9rem;color:#666;">风险等级</div>
        </div>
        """, unsafe_allow_html=True)
        if risk == 'HIGH' and decision == 'DENY':
            st.markdown('<div class="warn-banner">⚠️ 高危操作，系统自动拒绝</div>', unsafe_allow_html=True)
        elif risk == 'HIGH':
            st.markdown('<div class="warn-banner">⚠️ 高危操作，请严格执行操作票与监护制度</div>', unsafe_allow_html=True)
        
        # 操作信息卡片
        inject_css_file("assets/audit_report.css")
        st.markdown('''
        <div class="info-card">
            <div class="info-item"><span class="info-label">任务类型</span><span class="info-value">''' + task_type + '''</span></div>
            <div class="info-item"><span class="info-label">操作票号</span><span class="info-value">''' + ticket_no + '''</span></div>
            <div class="info-item"><span class="info-label">审核时间</span><span class="info-value">''' + ts + '''</span></div>
            <div class="info-item"><span class="info-label">操作人</span><span class="info-value">''' + operator + '''</span></div>
            <div class="info-item"><span class="info-label">电站</span><span class="info-value">''' + station + '''</span></div>
        </div>
        ''', unsafe_allow_html=True)
        st.markdown('**操作指令**')
        st.info(user_command)
    
    with rc:
        st.markdown('### 📄 审核报告')
        
        # 专家意见卡片
        st.markdown('''
        <div style="background:#e8f5e9;border-left:4px solid #4caf50;border-radius:4px;padding:12px 15px;margin:10px 0;">
            <div style="font-weight:600;color:#2e7d32;margin-bottom:8px;">✅ 正确操作（标准要点）</div>
            <div style="color:#333;line-height:1.6;">''' + fmt_text(results.get('expert', '')) + '''</div>
        </div>
        ''', unsafe_allow_html=True)
        
        # 蓝队意见卡片
        st.markdown('''
        <div style="background:#e3f2fd;border-left:4px solid #2196f3;border-radius:4px;padding:12px 15px;margin:10px 0;">
            <div style="font-weight:600;color:#1565c0;margin-bottom:8px;">⚠️ 涉及规程 / 条款</div>
            <div style="color:#333;line-height:1.6;">''' + fmt_text(results.get('blue', '')) + '''</div>
        </div>
        ''', unsafe_allow_html=True)
        
        # 红队意见卡片
        st.markdown('''
        <div style="background:#ffebee;border-left:4px solid #f44336;border-radius:4px;padding:12px 15px;margin:10px 0;">
            <div style="font-weight:600;color:#c62828;margin-bottom:8px;">⛔ 违反规则的具体行为</div>
            <div style="color:#333;line-height:1.6;">''' + fmt_text(results.get('red', '')) + '''</div>
        </div>
        ''', unsafe_allow_html=True)
        
        # 整改建议卡片
        st.markdown('''
        <div style="background:#fff3e0;border-left:4px solid #ff9800;border-radius:4px;padding:12px 15px;margin:10px 0;">
            <div style="font-weight:600;color:#e65100;margin-bottom:8px;">💡 整改建议</div>
            <div style="color:#333;line-height:1.6;">''' + fmt_text(dp.get('measures', '无')) + '''</div>
        </div>
        ''', unsafe_allow_html=True)
    
    with st.expander('⭐ 决策理由（全文）', expanded=False):
        st.markdown(results.get('decision', ''))
    st.divider()
    st.markdown('<div class="multi-agent-report">', unsafe_allow_html=True)
    st.markdown('<div class="report-header">🤖 多智能体协同审核报告</div>', unsafe_allow_html=True)
    st.markdown('<div class="agent-grid">', unsafe_allow_html=True)
    
    def esc(t): return html.escape(t or '').replace('\n', '<br/>')
    
    st.markdown(f'''
    <div class="agent-card auditor">
        <div class="agent-name">🔍 审核员</div>
        <div class="agent-content">{esc(results.get('auditor', ''))}</div>
    </div>
    <div class="agent-card red">
        <div class="agent-name">⚔️ 红队攻击手</div>
        <div class="agent-content">{esc(results.get('red', ''))}</div>
    </div>
    <div class="agent-card blue">
        <div class="agent-name">🛡️ 蓝队防御者</div>
        <div class="agent-content">{esc(results.get('blue', ''))}</div>
    </div>
    <div class="agent-card expert">
        <div class="agent-name">📚 规程专家</div>
        <div class="agent-content">{esc(results.get('expert', ''))}</div>
    </div>
    ''', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="agent-grid"><div class="agent-card decision">', unsafe_allow_html=True)
    st.markdown(f'<div class="agent-name">⚖️ 决策者</div><div class="agent-content">{results.get("decision", "")}</div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ================= 🤖 数据结构定义 =================
class AuditResult(BaseModel):
    decision: str = Field(description="ALLOW 或 DENY")
    risk_level: str = Field(description="HIGH/MEDIUM/LOW")
    confidence: int = Field(description="0-100")
    violation_rules: List[str] = Field(default_factory=list)

# ================= 📡 SCADA 数据接口 =================
class SCADADataFetcher:
    """110kV 变电站模拟数据生成器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.enabled = config.get('enabled', False)
        self.data_type = config.get('type', 'mock')
    
    def get_realtime_data(self) -> Dict:
        """生成真实感变电站模拟数据"""
        np.random.seed(int(datetime.now().timestamp()) % 1000)
        now = datetime.now()
        
        # 时间序列 - 最近2小时，每5分钟一个点
        time_points = pd.date_range(start=now - pd.Timedelta(hours=2), periods=24, freq='5min')
        
        # 110kV侧电压 (标准范围: 106.7~126.5kV)
        base_voltage_110 = 115.0
        voltage_110 = base_voltage_110 + np.cumsum(np.random.randn(24) * 0.3)
        voltage_110 = np.clip(voltage_110, 106, 126)
        
        # 35kV侧电压 (标准范围: 33.25~38.5kV)
        base_voltage_35 = 35.8
        voltage_35 = base_voltage_35 + np.cumsum(np.random.randn(24) * 0.15)
        voltage_35 = np.clip(voltage_35, 33, 39)
        
        # 10kV侧电压 (标准范围: 9.5~10.5kV)
        base_voltage_10 = 10.3
        voltage_10 = base_voltage_10 + np.cumsum(np.random.randn(24) * 0.1)
        voltage_10 = np.clip(voltage_10, 9.5, 10.8)
        
        # 主变电流 (A)
        current_t1 = 120 + np.cumsum(np.random.randn(24) * 3)
        current_t1 = np.clip(current_t1, 80, 180)
        current_t2 = 115 + np.cumsum(np.random.randn(24) * 3)
        current_t2 = np.clip(current_t2, 75, 170)
        
        # 有功功率 (MW)
        power_t1 = voltage_110[-1] * current_t1[-1] / 1000 * 0.85
        power_t2 = voltage_110[-1] * current_t2[-1] / 1000 * 0.85
        
        return {
            'source': self.data_type,
            'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
            'time_series': time_points,
            'time_points': time_points,
            # 电压等级
            'voltage_110': voltage_110,
            'voltage_35': voltage_35,
            'voltage_10': voltage_10,
            # 电流
            'current_t1': current_t1,
            'current_t2': current_t2,
            # 功率
            'power_t1': power_t1,
            'power_t2': power_t2,
            'total_power': power_t1 + power_t2,
            # 当前值
            'voltage': voltage_110[-1],  # 兼容原代码
            'current': current_t1[-1],      # 兼容原代码
            # 设备状态
            'devices': self._generate_device_status(time_points),
            # 告警
            'alarms': self._generate_alarms(now),
        }
    
    def _generate_device_status(self, time_points) -> List[Dict]:
        """生成设备状态"""
        return [
            {
                '设备': '1#主变 (110kV/35kV/10kV)',
                '状态': '运行',
                '负载率': f'{np.random.randint(65, 80)}%',
                '油温': f'{np.random.randint(42, 52)}°C',
                '侧电压': f'{np.random.uniform(113, 117):.1f}kV'
            },
            {
                '设备': '2#主变 (110kV/35kV/10kV)',
                '状态': '运行',
                '负载率': f'{np.random.randint(60, 75)}%',
                '油温': f'{np.random.randint(40, 50)}°C',
                '侧电压': f'{np.random.uniform(113, 117):.1f}kV'
            },
            {
                '设备': '110kV I段母线',
                '状态': '运行',
                '电压': f'{np.random.uniform(113, 117):.1f} kV',
                '频率': f'{np.random.uniform(49.95, 50.05):.2f} Hz'
            },
            {
                '设备': '35kV I段母线',
                '状态': '运行',
                '电压': f'{np.random.uniform(35.2, 36.2):.1f} kV',
                '频率': f'{np.random.uniform(49.95, 50.05):.2f} Hz'
            },
            {
                '设备': '10kV I段母线',
                '状态': '运行',
                '电压': f'{np.random.uniform(10.1, 10.5):.1f} kV',
                '负载率': f'{np.random.randint(55, 75)}%'
            },
        ]
    
    def _generate_alarms(self, now: datetime) -> List[Dict]:
        """生成告警信息"""
        alarms = []
        # 随机告警
        if np.random.random() > 0.7:
            alarms.append({
                '时间': now.strftime('%H:%M:%S'),
                '级别': 'warning',
                '设备': '10kV III段母线',
                '内容': '负载率偏高 (85%)',
                '建议': '关注负荷变化'
            })
        if np.random.random() > 0.8:
            alarms.append({
                '时间': now.strftime('%H:%M:%S'),
                '级别': 'info',
                '设备': '1#主变',
                '内容': '油温略高 (50°C)',
                '建议': '继续监测'
            })
        return alarms

# ===========================================================
# ================= 🤖 LangChain ReAct 智能体=================
# ===========================================================

# 工具列表（绑定到每个智能体）
AGENT_TOOLS = [
    search_regulations,
    check_five_preventions,
    analyze_topology,
    query_scada_status,
    validate_operation_compliance,
]

TOOL_MAP = {t.name: t for t in AGENT_TOOLS}


class PowerStationAgent:
   

    def __init__(
        self,
        name: str,
        system_prompt: str,
        api_key: str,
        base_url: str,
        model: str = "deepseek-chat",
        rag_kb=None,
        enable_cache: bool = True,
        max_retries: int = 1,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.rag_kb = rag_kb
        self.enable_cache = enable_cache
        self.max_retries = max_retries
        self._cache: Dict[str, str] = {}
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            llm_kwargs = {
                "model": self.model,
                "openai_api_key": self.api_key,
                "openai_api_base": self.base_url,
                "temperature": 0.2,
                "max_tokens": 260,
                "timeout": 20,
                "max_retries": 0,
            }
            if DEEPSEEK_THINKING in {"disabled", "off", "false", "0"}:
                llm_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            self._llm = ChatOpenAI(**llm_kwargs)
        return self._llm

    def run(self, user_input: str, context: Optional[Dict] = None) -> str:
        """执行智能体推理（单轮角色分析，复用共享工具上下文）"""
        ctx = context or {}
        shared_tool_context = str(ctx.get("shared_tool_context") or "").strip()
        rag_context = str(ctx.get("context") or "").strip()
        cache_src = json.dumps(
            {
                "name": self.name,
                "input": user_input,
                "shared_tool_context": shared_tool_context[:1800],
                "rag_context": rag_context[:600],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        cache_key = hashlib.sha256(cache_src.encode("utf-8")).hexdigest()
        if self.enable_cache and cache_key in self._cache:
            return self._cache[cache_key]

        if shared_tool_context:
            context_blocks = [f"【共享工具结果】\n{shared_tool_context}\n【/共享工具结果】"]
            context_blocks.append(f"【操作指令】\n{user_input}")
            input_text = "\n\n".join(context_blocks)
        else:
            rag_ctx = self._build_rag_context(user_input)
            input_text = f"{rag_ctx}\n\n操作指令：{user_input}" if rag_ctx else user_input

        last_err = None
        for attempt in range(self.max_retries):
            try:
                llm = self._get_llm()
                result = llm.invoke(
                    [
                        SystemMessage(content=self.system_prompt),
                        HumanMessage(content=input_text),
                    ]
                )
                output = result.content if hasattr(result, "content") else str(result)
                if isinstance(output, list):
                    output = "".join(str(item) for item in output)
                output = str(output).strip()
                if self.enable_cache:
                    self._cache[cache_key] = output
                return output
            except Exception as e:
                last_err = e
                time.sleep(1 * (attempt + 1))

        fallback = f"[{self.name} 调用失败：{last_err}]"
        return fallback

    def _rag_retrieve(self, query: str, top_k: int = 3) -> str:
        """从 RAG 知识库快速检索相关规程"""
        if not self.rag_kb:
            return ""
        try:
            docs = self.rag_kb.search(query, top_k=top_k, use_llm_embed=False)
            if not docs:
                return ""
            lines = [f"【{d['category']}】{d['title']}：{d['content'][:300]}" for d in docs]
            return "\n\n---\n".join(lines)
        except Exception:
            return ""

    def _build_rag_context(self, user_input: str) -> str:
        rag = self._rag_retrieve(user_input, top_k=3)
        if rag:
            return f"\n\n【RAG 检索参考】\n{rag}\n【/RAG 参考】"
        return ""


class AgentDebateSystem:
    """多智能体博弈系统 - 优化版（并行 + 精简）"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "deepseek-chat",
        rag_kb=None,
    ):
        if not api_key:
            raise ValueError("⚠️ API Key 未配置！")
        self.rag_kb = rag_kb
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

        self.agents = {
            "auditor": PowerStationAgent(
                name="👮 审核员",
                system_prompt="""你是变电站操作审核员。基于给定共享结果直接形成审核意见。
要求：
- 只写结论、依据、风险点
- 不写分析步骤，不写工具名和代码名
- 控制在80-120字""",
                api_key=api_key,
                base_url=base_url,
                model=model,
                rag_kb=rag_kb,
            ),
            "red": PowerStationAgent(
                name="🥷 红队攻击手",
                system_prompt="""你是电力安全红队攻击手。基于给定共享结果指出最危险的1-2个风险点。
要求：
- 只写风险点和后果
- 不写分析步骤，不写工具名和代码名
- 控制在60-100字""",
                api_key=api_key,
                base_url=base_url,
                model=model,
                rag_kb=rag_kb,
            ),
            "blue": PowerStationAgent(
                name="🛡️ 蓝队防御者",
                system_prompt="""你是蓝队防御者。基于给定共享结果做安规复核。
要求：
- 直接写是否违规、对应规则、风险等级
- 不写分析步骤，不写工具名和代码名
- 控制在60-100字""",
                api_key=api_key,
                base_url=base_url,
                model=model,
                rag_kb=rag_kb,
            ),
            "expert": PowerStationAgent(
                name="📚 规程专家",
                system_prompt="""你是电力安全规程专家。基于给定共享结果提炼条款依据和标准操作要点。
要求：
- 直接写专家意见
- 不写分析步骤，不写工具名和代码名
- 控制在60-100字""",
                api_key=api_key,
                base_url=base_url,
                model=model,
                rag_kb=rag_kb,
            ),
            "decision": PowerStationAgent(
                name="⚖️ 决策者",
                system_prompt="""你是最终决策者。综合共享结果和四个角色意见给出最终裁决。
规则：
- 仅按以下格式输出五行
决策：ALLOW 或 DENY
风险等级：HIGH 或 MEDIUM 或 LOW
置信度：0-100 的数字
违反规则：[规则列表，无则写无]
建议措施：[具体措施列表，无则写无]
- 不要输出任何额外解释""",
                api_key=api_key,
                base_url=base_url,
                model=model,
                rag_kb=rag_kb,
            ),
        }
    
    @staticmethod
    def _plain_for_chain(text: str) -> str:
        """链式传给下一智能体时去掉 Markdown 星号，减少噪声。"""
        if not text:
            return ""
        t = text.replace("**", "").replace("*", "")
        return t.strip()

    @staticmethod
    def _sanitize_agent_output(text: str) -> str:
        if not text:
            return ""
        cleaned = str(text)
        replacements = {
            "search_regulations": "规程检索",
            "check_five_preventions": "五防校验",
            "analyze_topology": "拓扑分析",
            "query_scada_status": "状态核对",
            "validate_operation_compliance": "合规校验",
            "_search_regulations_impl": "规程检索",
            "_analyze_topology_impl": "拓扑分析",
            "_query_scada_status_impl": "状态核对",
            "_validate_operation_compliance_impl": "合规校验",
        }
        for src, dst in replacements.items():
            cleaned = cleaned.replace(src, dst)

        cleaned = re.sub(r"\*\*第[一二三四五六七八九十]+步[:：]?\*\*", "", cleaned)
        cleaned = re.sub(r"第[一二三四五六七八九十]+步[:：]?", "", cleaned)
        cleaned = re.sub(r"使用(?:了)?[A-Za-z_][A-Za-z0-9_]*", "结合相关校验结果", cleaned)
        cleaned = re.sub(r"调用(?:了)?[A-Za-z_][A-Za-z0-9_]*", "结合相关校验结果", cleaned)
        cleaned = re.sub(r"好的，收到操作指令。?", "", cleaned)
        cleaned = re.sub(r"我将按照标准流程进行审核分析。?", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _parse_decision_output(decision_text: str) -> Dict:
        """解析决策者输出；兼容中英文冒号、空格及模型轻微格式偏差。"""
        raw = decision_text or ""
        t = raw.replace("：", ":")

        decision = "DENY"
        m = re.search(r"决策\s*:\s*(ALLOW|DENY)\b", t, re.IGNORECASE)
        if m:
            decision = m.group(1).upper()
        else:
            # 末段常见写法兜底
            tail = t[-800:] if len(t) > 800 else t
            if re.search(r"\bALLOW\b", tail, re.IGNORECASE) and not re.search(
                r"\bDENY\b", tail, re.IGNORECASE
            ):
                decision = "ALLOW"
            elif re.search(r"\bDENY\b", tail, re.IGNORECASE):
                decision = "DENY"

        risk = "MEDIUM"
        m = re.search(r"风险等级\s*:\s*(HIGH|MEDIUM|LOW)\b", t, re.IGNORECASE)
        if m:
            risk = m.group(1).upper()
        else:
            if re.search(r"(HIGH|高\s*风\s*险|高风险)", t, re.IGNORECASE):
                risk = "HIGH"
            elif re.search(r"(LOW|低\s*风\s*险|低风险)", t, re.IGNORECASE):
                risk = "LOW"

        confidence = 80
        m = re.search(r"置信度\s*:\s*(\d{1,3})\b", t)
        if m:
            confidence = max(0, min(100, int(m.group(1))))

        violations = "无"
        m = re.search(r"违反规则\s*:\s*\[([^\]]*)\]", t)
        if m:
            violations = m.group(1).strip() or "无"
        else:
            m2 = re.search(r"违反规则\s*:\s*([^\n]+)", t)
            if m2:
                violations = m2.group(1).strip() or "无"

        measures = "无"
        m = re.search(r"建议措施\s*:\s*\[([^\]]*)\]", t)
        if m:
            measures = m.group(1).strip() or "无"
        else:
            m2 = re.search(r"建议措施\s*:\s*([^\n]+)", t)
            if m2:
                measures = m2.group(1).strip() or "无"

        return {
            "decision": decision,
            "risk_level": risk,
            "confidence": confidence,
            "violations": violations,
            "measures": measures,
        }

    @staticmethod
    def _format_decision_output(parsed: Dict) -> str:
        return (
            f"决策：{parsed['decision']}\n"
            f"风险等级：{parsed['risk_level']}\n"
            f"置信度：{parsed['confidence']}\n"
            f"违反规则：[{parsed['violations']}]\n"
            f"建议措施：[{parsed['measures']}]"
        )

    @staticmethod
    def _apply_rule_based_override(command: str, task_type: str, parsed: Dict, tool_summary: Dict) -> Dict:
        final_parsed = dict(parsed or {})
        final_parsed.setdefault("decision", "DENY")
        final_parsed.setdefault("risk_level", "MEDIUM")
        final_parsed.setdefault("confidence", 80)
        final_parsed.setdefault("violations", "无")
        final_parsed.setdefault("measures", "无")

        if tool_summary.get("safe_to_allow"):
            final_parsed["decision"] = "ALLOW"
            final_parsed["risk_level"] = "LOW"
            final_parsed["confidence"] = max(int(final_parsed.get("confidence", 80)), 92)
            final_parsed["violations"] = "无"
            final_parsed["measures"] = "按票执行，继续落实监护、唱票复诵和现场状态确认。"
            return final_parsed

        if tool_summary.get("five_preventions_violations"):
            final_parsed["decision"] = "DENY"
            final_parsed["risk_level"] = "HIGH"
            final_parsed["violations"] = "；".join(tool_summary["five_preventions_violations"])
            final_parsed["measures"] = "消除五防风险后重新编制并审核操作票。"
            return final_parsed

        if tool_summary.get("compliance_issues"):
            final_parsed["decision"] = "DENY"
            if final_parsed.get("risk_level") == "LOW":
                final_parsed["risk_level"] = "MEDIUM"
            final_parsed["violations"] = "；".join(tool_summary["compliance_issues"])
            final_parsed["measures"] = "按安规修正操作票表述和步骤后重新审核。"
            return final_parsed

        if (
            final_parsed.get("decision") == "DENY"
            and "SCADA" in str(final_parsed.get("violations", ""))
            and tool_summary.get("five_preventions_ok")
            and tool_summary.get("compliance_ok")
        ):
            final_parsed["decision"] = "ALLOW"
            final_parsed["risk_level"] = "LOW"
            final_parsed["confidence"] = max(int(final_parsed.get("confidence", 80)), 88)
            final_parsed["violations"] = "无"
            final_parsed["measures"] = "模拟 SCADA 仅作参考，执行前按现场监护制度确认设备状态。"
        return final_parsed

    @staticmethod
    def _extract_scada_devices(command: str) -> List[str]:
        text = str(command or "")
        candidates = []
        pattern_groups = [
            r"\d+\s*线路",
            r"\d+\s*断路器",
            r"\d+\s*(?:线路侧|母线侧)?隔离开关",
            r"\d+\s*母线",
            r"\d+\s*主变",
        ]
        for pattern in pattern_groups:
            candidates.extend(re.findall(pattern, text))

        if "线路" in text and not any("线路" in item for item in candidates):
            candidates.append("线路")
        if "断路器" in text and not any("断路器" in item for item in candidates):
            candidates.append("断路器")
        if "隔离开关" in text and not any("隔离开关" in item for item in candidates):
            candidates.append("隔离开关")
        if "母线" in text and not any("母线" in item for item in candidates):
            candidates.append("母线")
        if "主变" in text and not any("主变" in item for item in candidates):
            candidates.append("主变")

        devices = []
        for item in candidates:
            item = re.sub(r"\s+", "", item)
            if item and item not in devices:
                devices.append(item)
        return devices[:3]

    @staticmethod
    def _shared_context_cache_key(command: str, context: Optional[Dict] = None) -> str:
        ctx = context or {}
        task_type = str(ctx.get("task_type") or "").strip()
        cached_context = str(ctx.get("context") or "").strip()
        key_src = json.dumps(
            {
                "task_type": task_type,
                "command": str(command or "").strip(),
                "context": cached_context[:500],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(key_src.encode("utf-8")).hexdigest()

    def _build_shared_tool_context(self, command: str, context: Optional[Dict] = None) -> str:
        ctx = context or {}
        task_type = str(ctx.get("task_type") or "")
        cache = st.session_state.setdefault("shared_tool_context_cache", {})
        cache_key = self._shared_context_cache_key(command, ctx)
        if cache_key in cache:
            return cache[cache_key]

        query = f"{task_type} {command}".strip()
        sections = []
        if task_type:
            sections.append(f"【任务类型】\n{task_type}")
        if ctx.get("context"):
            preview = str(ctx["context"]).replace("\n", " ").strip()[:260]
            sections.append(f"【规程检索】\n{preview}")
        else:
            sections.append(f"【规程检索】\n{_search_regulations_impl(query, use_llm_embed=False)}")
        sections.append(f"【五防校验】\n{_format_five_preventions_result(command)}")
        sections.append(f"【拓扑分析】\n{_analyze_topology_impl(command)}")
        sections.append(f"【合规校验】\n{_format_operation_compliance_result(command)}")

        scada_sections = []
        for device in self._extract_scada_devices(command):
            scada_sections.append(_query_scada_status_impl(device))
        if scada_sections:
            sections.append("【SCADA 快照】\n" + "\n\n".join(scada_sections))
        shared_context = "\n\n".join(sections)[:1800]
        cache[cache_key] = shared_context
        if len(cache) > 30:
            oldest_key = next(iter(cache))
            cache.pop(oldest_key, None)
        return shared_context

    def run_debate(self, command: str, context: Optional[Dict] = None) -> Dict:
        """执行多智能体博弈（优化：并行 + 精简输出）"""
        results: Dict = {}
        ctx = context or {}
        audit_id = ctx.get("audit_id") or f"AUDIT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        task_type = ctx.get("task_type", "")
        tool_summary = _build_rule_based_audit_summary(command, task_type)

        _set_active_scada_context(audit_id, command, task_type)

        try:
            shared_tool_context = self._build_shared_tool_context(command, ctx)
            shared_ctx = dict(ctx)
            shared_ctx["shared_tool_context"] = shared_tool_context
            results["shared_tool_context"] = shared_tool_context

            # 1. 四个角色基于同一份共享工具结果并行分析
            with ThreadPoolExecutor(max_workers=4) as pool:
                auditor_future = pool.submit(self.agents["auditor"].run, command, shared_ctx)
                red_future = pool.submit(
                    self.agents["red"].run,
                    f"操作指令：{command}\n请从攻击者角度分析风险（100字内）。",
                    shared_ctx,
                )
                blue_future = pool.submit(
                    self.agents["blue"].run,
                    f"操作指令：{command}\n请从防御者角度指出违规风险（100字内）。",
                    shared_ctx,
                )
                expert_future = pool.submit(
                    self.agents["expert"].run,
                    f"操作指令：{command}\n请提供安规依据（100字内）。",
                    shared_ctx,
                )

                results["auditor"] = auditor_future.result()
                results["red"] = red_future.result()
                results["blue"] = blue_future.result()
                results["expert"] = expert_future.result()

            results["auditor"] = self._sanitize_agent_output(results["auditor"])
            results["red"] = self._sanitize_agent_output(results["red"])
            results["blue"] = self._sanitize_agent_output(results["blue"])
            results["expert"] = self._sanitize_agent_output(results["expert"])

            a = self._plain_for_chain(results["auditor"])
            r = self._plain_for_chain(results["red"])
            b = self._plain_for_chain(results["blue"])
            e = self._plain_for_chain(results["expert"])

            # 2. 决策者（综合所有意见）
            debate_summary = f"""操作指令：{command}
一审（审核员）：{a}
二审（红队）：{r}
三审（蓝队）：{b}
专家意见：{e}
统一规则校验：
- 五防校验：{"未发现明显违反" if tool_summary['five_preventions_ok'] else "；".join(tool_summary['five_preventions_violations'])}
- 合规校验：{"未发现明显违规" if tool_summary['compliance_ok'] else "；".join(tool_summary['compliance_issues'])}
- 标准顺序识别：{"；".join(tool_summary['matched_patterns']) if tool_summary['matched_patterns'] else "未命中明确标准顺序"}
注意：模拟 SCADA 仅作参考，不能单独作为 DENY 依据。
请给出最终决策。"""
            agent_outputs = [results.get("auditor", ""), results.get("red", ""), results.get("blue", ""), results.get("expert", "")]
            all_agents_failed = agent_outputs and all(str(item).startswith("[") for item in agent_outputs)
            if all_agents_failed or not LLM_FINAL_DECISION:
                results["decision"] = (
                    "决策：DENY\n风险等级：MEDIUM\n置信度：80\n"
                    "违反规则：[以本地规则校验为准]\n建议措施：[按规则校验结果执行]"
                )
            else:
                results["decision"] = self.agents["decision"].run(debate_summary, shared_ctx)
            results["tool_summary"] = tool_summary
            results["decision_raw"] = results["decision"]
            parsed = self._parse_decision_output(results["decision"])
            results["decision_parsed"] = self._apply_rule_based_override(command, task_type, parsed, tool_summary)
            results["decision"] = self._format_decision_output(results["decision_parsed"])
            return results
        finally:
            _clear_active_scada_context(audit_id)

# ================= 登录页 =================
if not st.session_state.authenticated:
    render_login_page(
        verify_user=verify_user,
        update_last_login=update_last_login,
    )

if st.session_state.authenticated:
    render_app_header()
    render_sidebar(
        effective_api_key=st.session_state.get("api_key") or DEEPSEEK_API_KEY or "",
        app_version=APP_VERSION,
        last_update=LAST_UPDATE,
    )

    if st.session_state.current_page == "home":
        render_home_page()
    elif st.session_state.current_page == "系统配置":
        render_system_config_page(DEEPSEEK_API_KEY)
    elif st.session_state.current_page == "操作审核":
        render_operation_audit_page(
            get_kb=_get_kb,
            agent_debate_system_cls=AgentDebateSystem,
            api_key=st.session_state.get("api_key") or DEEPSEEK_API_KEY or "",
            api_base_url=DEEPSEEK_BASE_URL,
            save_audit_record=save_audit_record,
            generate_alarm_from_audit=generate_alarm_from_audit,
            generate_audit_report_pdf=generate_audit_report_pdf,
            risk_label_and_color=_risk_label_and_color,
        )
    elif st.session_state.current_page == "审核历史":
        render_audit_history_page(
            get_audit_records=get_audit_records,
            risk_label_and_color=_risk_label_and_color,
        )
    elif st.session_state.current_page == "操作票管理":
        render_ticket_page(
            model_name=MODEL_NAME,
            api_key=st.session_state.get("api_key") or DEEPSEEK_API_KEY,
            api_base_url=DEEPSEEK_BASE_URL,
            save_operation_ticket=save_operation_ticket,
            get_operation_tickets=get_operation_tickets,
            generate_operation_ticket_pdf=generate_operation_ticket_pdf,
            pdf_available=_PDF_AVAILABLE,
        )
    elif st.session_state.current_page == "告警中心":
        render_alarm_page(
            get_alarm_stats=get_alarm_stats,
            get_alarms=get_alarms,
            update_alarm_status=update_alarm_status,
            save_alarm=save_alarm,
            get_app_db=_get_app_db,
        )
    elif st.session_state.current_page == "统计分析":
        render_stats_page(
            get_audit_stats=get_audit_stats,
            get_audit_records=get_audit_records,
        )
    elif st.session_state.current_page == "规程问答":
        render_qa_page(
            get_kb=_get_kb,
            model_name=MODEL_NAME,
            api_key=st.session_state.get("api_key") or DEEPSEEK_API_KEY,
            api_base_url=DEEPSEEK_BASE_URL,
        )
    elif st.session_state.current_page == "知识库管理":
        render_knowledge_base_page(get_kb=_get_kb)
    elif st.session_state.current_page == "用户管理":
        render_user_management_page(
            get_all_users=get_all_users,
            delete_user=delete_user,
            update_user_password=update_user_password,
            add_user=add_user,
            verify_user=verify_user,
            get_app_db=_get_app_db,
        )

st.divider()
st.markdown(
    f"<div style='text-align: center; color: #999; padding: 20px;'><p>智电卫士 | 框架：LangChain + Streamlit &nbsp;版本：{APP_VERSION} &nbsp;最后更新：{LAST_UPDATE}</p></div>",
    unsafe_allow_html=True,
)
