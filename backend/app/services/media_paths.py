"""Helpers for safe runtime media paths."""

from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil


def normalize_relative_media_path(path: str | None) -> str | None:
    """Return a safe POSIX-style relative media path, or None."""
    if path is None:
        return None

    raw = str(path).strip()
    if not raw:
        return None

    windows_path = PureWindowsPath(raw)
    if windows_path.drive or windows_path.is_absolute():
        return None

    normalized = raw.replace("\\", "/")
    if PurePosixPath(normalized).is_absolute():
        return None

    parts: list[str] = []
    for part in normalized.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)

    if not parts:
        return None
    return "/".join(parts)


def copy_asset_to_runtime(
    source_path: str | Path,
    media_root: str | Path,
    bank_id: str,
    asset_type: str,
    filename: str,
) -> str:
    """Copy an asset into runtime media and return its /images-relative path."""
    source = Path(source_path)
    root = Path(media_root)

    safe_bank = _safe_path_component(bank_id, fallback="bank")
    safe_type = _safe_path_component(asset_type, fallback="assets")
    safe_name = _safe_filename(filename)

    dest = root / safe_bank / safe_type / safe_name
    root_resolved = root.resolve(strict=False)
    dest_resolved = dest.resolve(strict=False)
    try:
        dest_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("Resolved media destination escapes media_root") from exc

    dest_resolved.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest_resolved)

    return f"question_assets/{safe_bank}/{safe_type}/{safe_name}"


def _safe_filename(filename: str) -> str:
    leaf = str(filename or "").strip().replace("\\", "/").split("/")[-1]
    return _safe_path_component(leaf, fallback="asset")


def _safe_path_component(value: str, fallback: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    safe_parts: list[str] = []
    for part in raw.split("/"):
        part = part.strip()
        if part in ("", ".", ".."):
            continue
        part = part.replace("..", "_").replace(":", "_")
        part = part.strip(" .")
        if part:
            safe_parts.append(part)

    return "_".join(safe_parts) or fallback
