"""Generate a quality-control report for the imported question bank."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "app_questions.db"
DEFAULT_IMAGE_ROOT = PROJECT_ROOT / "images"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "reports"

MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
CODE_FENCE_RE = re.compile(r"```")


@dataclass(frozen=True)
class Issue:
    issue_type: str
    question_id: int | None
    severity: str
    subject: str | None
    chapter: str | None
    source_pdf: str | None
    page_number: int | None
    detail: str
    preview: str


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _preview(text: str | None, limit: int = 160) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _question_issue(row: sqlite3.Row, issue_type: str, severity: str, detail: str) -> Issue:
    return Issue(
        issue_type=issue_type,
        question_id=row["id"],
        severity=severity,
        subject=row["subject"],
        chapter=row["chapter"],
        source_pdf=row["source_pdf"],
        page_number=row["page_number"],
        detail=detail,
        preview=_preview(row["question_text"]),
    )


def _iter_questions(con: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    return con.execute(
        """
        select
            id, subject, chapter, question_type, question_text,
            option_a, option_b, option_c, option_d,
            answer, image_path, source_pdf, page_number
        from questions
        order by id
        """
    )


def collect_issues(con: sqlite3.Connection, image_root: Path) -> list[Issue]:
    issues: list[Issue] = []
    asset_counts = {
        row["question_id"]: row["count"]
        for row in con.execute(
            """
            select question_id, count(*) as count
            from question_assets
            group by question_id
            """
        )
    }

    for row in _iter_questions(con):
        text = row["question_text"] or ""

        if row["question_type"] == "choice":
            missing = [
                label
                for label, field in (
                    ("A", "option_a"),
                    ("B", "option_b"),
                    ("C", "option_c"),
                    ("D", "option_d"),
                )
                if not (row[field] or "").strip()
            ]
            if missing:
                issues.append(
                    _question_issue(
                        row,
                        "choice_missing_option",
                        "high",
                        "Missing option(s): " + ",".join(missing),
                    )
                )

        if not (row["answer"] or "").strip():
            issues.append(
                _question_issue(
                    row,
                    "empty_answer",
                    "info",
                    "Answer is empty; expected before DeepSeek answer generation.",
                )
            )

        image_refs = MARKDOWN_IMAGE_RE.findall(text)
        if image_refs:
            severity = "medium" if asset_counts.get(row["id"], 0) == 0 else "info"
            issues.append(
                _question_issue(
                    row,
                    "markdown_image_reference",
                    severity,
                    f"Text contains {len(image_refs)} markdown image reference(s); assets={asset_counts.get(row['id'], 0)}.",
                )
            )

        if "<table" in text.lower() or "</table>" in text.lower():
            issues.append(
                _question_issue(
                    row,
                    "raw_html_table",
                    "medium",
                    "Question text contains raw HTML table markup.",
                )
            )

        if "\\begin{array}" in text or "\\end{array}" in text:
            issues.append(
                _question_issue(
                    row,
                    "latex_array",
                    "medium",
                    "Question text contains LaTeX array markup.",
                )
            )

        if "<details" in text.lower() or "```mermaid" in text.lower():
            issues.append(
                _question_issue(
                    row,
                    "mineru_details_or_mermaid",
                    "medium",
                    "Question text contains MinerU details/mermaid block.",
                )
            )

        if len(CODE_FENCE_RE.findall(text)) % 2:
            issues.append(
                _question_issue(
                    row,
                    "unbalanced_code_fence",
                    "high",
                    "Odd number of markdown code fences.",
                )
            )

        if len(text) > 3000:
            issues.append(
                _question_issue(
                    row,
                    "very_long_question_text",
                    "medium",
                    f"Question text is {len(text)} characters.",
                )
            )

    for asset in con.execute(
        "select id, question_id, path, page_no, source_type from question_assets order by id"
    ):
        candidate = image_root / asset["path"]
        if not candidate.exists():
            issues.append(
                Issue(
                    issue_type="missing_asset_file",
                    question_id=asset["question_id"],
                    severity="critical",
                    subject=None,
                    chapter=None,
                    source_pdf=None,
                    page_number=asset["page_no"],
                    detail=f"Asset row {asset['id']} points to missing file: {asset['path']}",
                    preview="",
                )
            )

    return issues


def collect_summary(con: sqlite3.Connection, image_root: Path, issues: list[Issue]) -> dict:
    by_issue: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for issue in issues:
        by_issue[issue.issue_type] = by_issue.get(issue.issue_type, 0) + 1
        by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1

    physical_asset_files = 0
    asset_dir = image_root / "question_assets"
    if asset_dir.exists():
        physical_asset_files = sum(1 for path in asset_dir.rglob("*") if path.is_file())

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "questions_total": con.execute("select count(*) from questions").fetchone()[0],
        "assets_total": con.execute("select count(*) from question_assets").fetchone()[0],
        "physical_asset_files": physical_asset_files,
        "by_subject_type": [
            dict(row)
            for row in con.execute(
                """
                select subject, question_type, count(*) as count
                from questions
                group by subject, question_type
                order by subject, question_type
                """
            )
        ],
        "by_source": [
            dict(row)
            for row in con.execute(
                """
                select source_pdf, count(*) as count
                from questions
                group by source_pdf
                order by source_pdf
                """
            )
        ],
        "issues_by_type": dict(sorted(by_issue.items())),
        "issues_by_severity": dict(sorted(by_severity.items())),
    }


def write_reports(report_dir: Path, summary: dict, issues: list[Issue]) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"question_bank_qc_{stamp}.json"
    csv_path = report_dir / f"question_bank_qc_issues_{stamp}.csv"
    md_path = report_dir / f"question_bank_qc_{stamp}.md"

    payload = {"summary": summary, "issues": [asdict(issue) for issue in issues]}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(issues[0]).keys()) if issues else list(Issue.__annotations__))
        writer.writeheader()
        for issue in issues:
            writer.writerow(asdict(issue))

    lines = [
        "# Question Bank QC Report",
        "",
        f"- Generated at: {summary['generated_at']}",
        f"- Questions: {summary['questions_total']}",
        f"- Asset rows: {summary['assets_total']}",
        f"- Physical asset files: {summary['physical_asset_files']}",
        "",
        "## Issues By Severity",
        "",
    ]
    for severity, count in summary["issues_by_severity"].items():
        lines.append(f"- {severity}: {count}")

    lines.extend(["", "## Issues By Type", ""])
    for issue_type, count in summary["issues_by_type"].items():
        lines.append(f"- {issue_type}: {count}")

    lines.extend(["", "## High/Critical Issues", ""])
    important = [issue for issue in issues if issue.severity in {"critical", "high"}]
    if not important:
        lines.append("No high or critical issues found.")
    else:
        for issue in important[:200]:
            lines.append(
                f"- Q{issue.question_id}: {issue.issue_type} | {issue.detail} | "
                f"{issue.subject or ''} / {issue.chapter or ''} | {issue.preview}"
            )
        if len(important) > 200:
            lines.append(f"- ... {len(important) - 200} more")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "markdown": md_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--image-root", type=Path, default=DEFAULT_IMAGE_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()

    con = _connect(args.db)
    try:
        issues = collect_issues(con, args.image_root)
        summary = collect_summary(con, args.image_root, issues)
        paths = write_reports(args.report_dir, summary, issues)
    finally:
        con.close()

    print(json.dumps({"summary": summary, "reports": {k: str(v) for k, v in paths.items()}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
