# 408考研AI专属助教

一款面向计算机考研408统考的智能刷题与错题分析工具。支持从 PDF 题库批量导入题目，提供在线刷题、AI助教答疑、薄弱知识点分析和错题集管理等功能。

## 功能概览

**题库导入** — 上传王道等408题库 PDF，自动解析选择题和综合题，识别科目、章节、知识点标签并入库。支持 PUA 乱码检测和自动修复。

**刷题练习** — 按科目/章节随机或顺序刷题，即时批改并显示正确答案与解析。支持批量刷题模式和进度追踪。

**答题统计** — 追踪各科正确率变化趋势，智能分析薄弱知识点，按知识点维度统计掌握情况。

**AI助教** — 基于 DeepSeek 大模型的智能问答，可针对具体题目或知识点进行深入讲解和答疑。

**错题集** — 答错题目自动收集，支持按科目/章节/状态筛选，逐题或批量重做，状态标记（已掌握/待巩固/未重做），手动添加和移除。

**知识盲区分析** — AI 自动分析错题中的知识盲区和常见误区，生成纠正建议和记忆方法。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 前端框架 | Streamlit (赛博朋克暗黑主题) |
| 数据库 | SQLite + SQLAlchemy 2.0 (ORM) |
| PDF解析 | PyMuPDF |
| AI模型 | DeepSeek API (OpenAI 兼容接口) |
| 架构模式 | Model → Repository → Service → Router 分层架构 |

## 快速开始

### 环境要求

- Python 3.11+
- pip

### 1. 克隆项目

```bash
git clone https://github.com/qmgk-source/408-ai-tutor.git
cd 408-ai-tutor
```

### 2. 安装依赖

```bash
# 后端依赖
pip install -r backend/requirements.txt

# 前端依赖
pip install -r frontend/requirements.txt
```

### 3. 配置环境变量

复制环境变量模板并填入你的 API Key：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# DeepSeek API 配置
# 获取地址: https://platform.deepseek.com/api_keys
LLM_API_BASE=https://api.deepseek.com
LLM_API_KEY=sk-your-api-key-here
LLM_MODEL=deepseek-chat

# 调试模式 (首次运行建议开启，自动创建数据库表)
DEBUG=true
LOG_LEVEL=INFO
```

### 4. 启动应用

```bash
python start.py
```

启动后自动打开浏览器，访问以下地址：

- 前端界面：http://127.0.0.1:8501
- 后端 API：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs

### 5. 导入题库

在前端「题库导入」页面上传你的408题库 PDF 文件，系统会自动解析题目并入库。

也可以在命令行批量导入：

```bash
python import_pdfs.py --pdf-dir /path/to/your/pdf/folder
```

## 项目结构

```
408-ai-tutor/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/               # 路由层 (6组API端点)
│   │   ├── core/              # 核心模块 (日志、异常)
│   │   ├── database/          # 数据库连接与会话管理
│   │   ├── models/            # ORM 模型 (5张表)
│   │   ├── repositories/      # 数据访问层
│   │   ├── schemas/           # Pydantic 数据校验
│   │   ├── services/          # 业务逻辑层
│   │   ├── utils/             # 工具函数
│   │   ├── config.py          # 应用配置
│   │   └── main.py            # FastAPI 入口
│   ├── tests/                 # 单元测试
│   └── requirements.txt
├── frontend/                   # Streamlit 前端
│   ├── app.py                 # 首页入口
│   ├── shared/                # 共享样式 (赛博朋克CSS)
│   ├── pages/                 # 5个功能页面
│   ├── .streamlit/            # Streamlit 主题配置
│   └── requirements.txt
├── scripts/                    # 辅助脚本
├── data/                       # 数据库文件 (运行时生成)
├── images/                     # 题目图片 (导入时提取)
├── logs/                       # 日志文件
├── start.py                    # 一键启动脚本
├── import_pdfs.py              # 命令行PDF批量导入
├── .env.example                # 环境变量模板
└── docker-compose.yml          # Docker 部署
```

## 数据库设计

| 表名 | 说明 |
|------|------|
| `questions` | 题目主表 (题干、选项、答案、解析、图片、溯源) |
| `quiz_records` | 作答记录 (每次答题的详细结果) |
| `misconceptions` | 知识盲区 (AI分析的错误模式和纠正建议) |
| `weak_knowledge` | 薄弱知识点 (按知识点维度统计正确率) |
| `wrong_questions` | 错题集 (自动收集+手动管理，支持重做追踪) |

## API 概览

| 模块 | 前缀 | 说明 |
|------|------|------|
| 题库导入 | `/api/import` | PDF上传、目录批量导入、导入报告 |
| 题目管理 | `/api/questions` | 题目CRUD、按科目/章节/题型查询 |
| 刷题练习 | `/api/quiz` | 抽题、提交答案、批次刷题 |
| AI助教 | `/api/tutor` | 智能问答对话 |
| 知识盲区 | `/api/misconceptions` | 盲区列表、统计分析 |
| 错题集 | `/api/wrong-questions` | 错题管理、重做、批量操作 |

完整 API 文档启动后访问 http://127.0.0.1:8000/docs

## Docker 部署 (可选)

```bash
# 构建并启动
docker-compose up -d

# 访问
# 前端: http://localhost:8501
# 后端: http://localhost:8000
```

首次运行需在 `.env` 中配置 API Key，Docker 会自动挂载 `data/` 目录持久化数据。

## 开发说明

```bash
# 运行后端测试
cd backend
pytest -v

# 单独启动后端
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 单独启动前端
cd frontend
streamlit run app.py --server.port 8501
```

## 常见问题

**Q: AI助教功能需要联网吗？**
A: 需要。AI助教和知识盲区分析依赖 DeepSeek API，需要有效的 API Key 和网络连接。刷题和题库管理功能可以离线使用。

**Q: 支持哪些PDF格式？**
A: 支持标准 PDF 格式的题库文件。对于扫描件（图片型PDF），系统会尝试 OCR 提取文本。推荐使用文字型 PDF 以获得最佳解析效果。

**Q: 数据库文件在哪里？**
A: 默认在 `data/questions.db`，SQLite 单文件数据库，备份只需复制该文件。

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。
