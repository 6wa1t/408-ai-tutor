# Release Notes

## v0.2.3 - 文档 overhaul + Agent 导出系统 + 题库共享 + Docker 修复

### 重点变更

- 新增 `tools/bank_builder/` 本地题库包构建器：将 MinerU Markdown 输出转换为自包含、可导入的 `bank.db` 题库包，含元数据、SHA-256 校验和与 QC 报告。入口：`python -m tools.bank_builder.build_bank`。
- 新增 Agent 笔记导出系统：`/api/agent-exports` API（POST 生成 + GET 列表）与 `scripts/export_agent_notes.py` 命令行工具，可生成错题、薄弱知识点、误区分析的 Markdown/JSON 快照，供桌面 Agent 消费。
- 新增 3 张数据库表：`chat_messages`（对话消息，与 conversations 一对多）、`review_notes`（复习笔记，关联 weak_knowledge）、`agent_exports`（导出运行记录）。
- **题库导出增强**：`BankService.export_bank()` 现在导出 3 张表（questions、question_assets、answer_candidates）并复制媒体文件到 `media/images/`。内置题库包从仅含题目文本升级为包含完整题目、图片资产和答案候选的自包含包。
- **4 个题库包推送到 GitHub**：数据结构 803 题、操作系统 752 题、组成原理 677 题、计网 640 题（共 2872 题），含 195 张图片和部分答案候选。用户 clone 后在「自选题库」Tab 直接导入即可使用，无需自行提取 PDF。
- 更新 `.gitignore`：新增 `!question_banks/**/*.db` 例外规则，允许 bank.db 被 Git 跟踪（全局 `*.db` 规则仍然排除运行时数据库）。
- README 全面更新：修复乱码段、API 数量 8→9 组、数据库表 9→12 张、项目结构补全 tools/docs/exports/scripts 详解、发布说明改为中文、补充题库共享功能说明和 Docker 兼容性。
- 修复 `docker-compose.yml`：为 backend 新增 `./exports:/app/exports` 卷挂载，确保容器内 Agent 笔记导出持久化到宿主机。
- 技术栈表补充 Markdown 解析条目；FAQ 新增"如何从 MinerU 输出构建题库包"问答。

### 验证

- Docker 部署全流程验证通过：`docker compose up -d --build` 构建成功，后端 healthy，前端 HTTP 200。
- 36 个 API 端点全部注册，含新增 `/api/agent-exports`。
- 题目库 2872 道题（操作系统 752 / 数据结构 803 / 组成原理 677 / 计网 640），随机抽题正常。
- 4 个题库包已推送到 GitHub，含 bank.db（3 表）、media/images/ 图片、metadata.json 和 manifest.json。
- 容器内 `/app/exports/` 和 `/app/question_banks/` 卷挂载确认生效，题库导入流程在 Docker 中正常工作。
- 答案迁移：从旧 `data/questions.db` 迁移 398 条答案到运行时数据库，操作系统和组成原理题库包含部分预置答案。

### 已知后续

- 数据结构和计网题库的答案仍为空，待 DeepSeek 答案候选工作流生成（首次作答时自动调用）。
- QC 报告仍标记不完整选择题解析候选供手动修复，未自动删除或修正。
- `config.py` 中 `app_version` 仍为 `0.2.2`，下次发布时需同步更新。
- 运行时数据库曾出现 SQLite B-tree 损坏（2876→2872 题，丢失 4 道），已通过 `iterdump()` 重建修复。

---

## v0.2.2 - MinerU high-accuracy import and rendering hardening

### Highlights

- Added a local high-accuracy MinerU workflow for scanned PDF question-bank extraction, including GPU-oriented execution settings in `scripts/run_mineru_questions_gpu.ps1`.
- Imported the Wangdao question-bank extraction result into the runtime SQLite database with 2876 questions and 195 indexed question assets.
- Added `scripts/qc_question_bank.py` to generate repeatable QC reports after import. Reports are emitted as Markdown, CSV, and JSON under `data/reports/`.
- Hardened Streamlit practice rendering for imported MinerU content:
  - strips Markdown image references from question text and renders assets separately;
  - removes MinerU `<details>` blocks such as `flowchart`, `text_image`, and Mermaid auxiliary descriptions;
  - preserves safe HTML tables while sanitizing table markup;
  - converts LaTeX arrays and table-cell LaTeX into readable table/text output;
  - repairs common broken code fences and inline assembly/code snippets.
- Updated backend practice queries so incomplete choice questions missing A/B/C/D are excluded from normal choice practice while remaining available in the database and QC reports.

### Validation

- `pytest -q --basetemp .pytest-tmp-qc backend/tests/test_frontend_question_rendering.py backend/tests/test_markdown_import_assets.py backend/tests/test_question_assets_api_shape.py`
- Latest result: 22 passed, 1 warning.
- Full-bank rendering scan currently reports zero leaked `<details>`, `<summary>`, Mermaid blocks, raw Markdown images, raw LaTeX arrays, unbalanced code fences, or table-cell LaTeX command residue.

### Known Follow-Ups

- Answers and explanations are intentionally still empty for the imported bank. They should be generated later through the DeepSeek answer-candidate workflow and user confirmation.
- QC reports currently flag incomplete choice parsing candidates for manual repair; these are not deleted or silently corrected.
- GitHub publishing is blocked in this local workspace until the Git metadata and GitHub CLI authentication are restored.
