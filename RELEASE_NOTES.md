# Release Notes

## v0.2.3 - MinerU high-accuracy import and rendering hardening

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
- Latest result: 25 passed, 1 warning.
- Full-bank rendering scan currently reports zero leaked `<details>`, `<summary>`, Mermaid blocks, raw Markdown images, raw LaTeX arrays, unbalanced code fences, or table-cell LaTeX command residue.

### Known Follow-Ups

- Answers and explanations are intentionally still empty for the imported bank. They should be generated later through the DeepSeek answer-candidate workflow and user confirmation.
- QC reports currently flag incomplete choice parsing candidates for manual repair; these are not deleted or silently corrected.
- GitHub publishing is blocked in this local workspace until the Git metadata and GitHub CLI authentication are restored.
