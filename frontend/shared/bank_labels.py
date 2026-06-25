"""Helpers for formatting built-in bank labels."""


def _value_or_default(value, default):
    return default if value in (None, "") else value


def format_bank_option_label(bank: dict) -> str:
    """Format a built-in bank manifest entry for the import selector."""
    q_count = _value_or_default(bank.get("question_count"), bank.get("count", 0))
    q_count = _value_or_default(q_count, 0)
    name = _value_or_default(bank.get("name"), bank.get("id", "unknown"))
    subject = _value_or_default(bank.get("subject"), "?")
    version = _value_or_default(bank.get("version"), "unknown")
    qc = _value_or_default(bank.get("qc_status"), "unknown")
    media = "有图表" if bank.get("has_media") else "无图表"
    answers = "含部分答案" if bank.get("has_partial_answers") else "无内置答案"

    return (
        f"{name} — {subject} · {q_count} 题 · v{version} · "
        f"{media} · {answers} · QC:{qc}"
    )
