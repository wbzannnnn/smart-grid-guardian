# 智电卫士

基于多智能体协同与 RAG 的变电站防误操作智能审核系统。

> 2026 中国大学生计算机设计大赛西北地区赛二等奖作品。

## 功能亮点

- 审核员、红队、蓝队、规程专家、决策者五角色协同审核
- SQLite + TF-IDF + Embedding 双索引规程知识库
- 五防规则校验、设备拓扑分析、操作合规验证
- 模拟 SCADA 状态查询与规则二次校验
- 审核历史、操作票、告警、统计分析和 PDF 报告
- Streamlit 多页面交互与用户权限管理

## 技术栈

Python、Streamlit、LangChain、DeepSeek API、RAG、SQLite、NumPy、Pandas、ReportLab

## 本地运行

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

配置环境变量：

```powershell
$env:DEEPSEEK_API_KEY="你的新 Key"
streamlit run app.py
```

打开 `http://localhost:8501`。

默认演示账号：

- 管理员：`admin / admin`
- 操作员：`operator / operator`

请勿将默认账号用于真实生产系统。

## Streamlit Community Cloud 部署

1. 将本仓库上传到 GitHub。
2. 打开 Streamlit Community Cloud，选择 **Create app**。
3. 选择仓库、默认分支和入口文件 `app.py`。
4. 在 **App settings → Secrets** 中粘贴：

```toml
DEEPSEEK_API_KEY = "新建的 DeepSeek API Key"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
MODEL_NAME = "deepseek-chat"
```

5. 点击 Deploy，等待生成 `https://*.streamlit.app` 公开链接。

## 部署说明

- 不配置 DeepSeek Key 时，登录、页面浏览、知识库管理和规则功能仍可使用，但多智能体大模型审核与问答不可用。
- Community Cloud 本地磁盘可能随应用重启而重置，SQLite 数据适合演示，不适合作为长期生产存储。
- SCADA 为模拟数据，本项目用于方案验证和竞赛演示，不可替代真实电力生产安全系统。

## 安全

仓库不包含 API Key。若某个 Key 曾经写入源码，请立即在服务商控制台吊销并重新生成。
