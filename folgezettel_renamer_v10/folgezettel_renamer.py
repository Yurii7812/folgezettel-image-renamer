from __future__ import annotations

import json
import os
import re
import sys
import traceback
import unicodedata
from datetime import datetime
import tkinter as tk
from dataclasses import dataclass, asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Pillowが必要です",
        "画像表示に必要なPillowが入っていません。\nrun.batから起動するか、次を実行してください。\n\npy -m pip install Pillow",
    )
    raise

APP_TITLE = "Folgezettel画像リネーマー"
PROJECT_FILE = ".folgezettel_project.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
ID_PATTERN = re.compile(r"^\d+(?:[a-z]+\d+)*[a-z]*$")
INVALID_WINDOWS_CHARS = set('<>:"/\\|?*')
FOLGEZETTEL_ID_RE = r"\d+(?:[a-z]+\d+)*[a-z]*"
DATE_IN_NAME_RE = re.compile(r"(?<!\d)(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])-(?P<day>0[1-9]|[12]\d|3[01])(?!\d)")

MD_PARENT_START = "<!-- FOLGEZETTEL:PARENT:START -->"
MD_PARENT_END = "<!-- FOLGEZETTEL:PARENT:END -->"
MD_CHILD_START = "<!-- FOLGEZETTEL:CHILD:START -->"
MD_CHILD_END = "<!-- FOLGEZETTEL:CHILD:END -->"
MD_BACKLINK_START = "<!-- FOLGEZETTEL:BACKLINK:START -->"
MD_BACKLINK_END = "<!-- FOLGEZETTEL:BACKLINK:END -->"


def natural_key(text: str):
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text)]


def increment_letters(letters: str) -> str:
    """a→b, z→aa, az→ba のように英字列を進める。"""
    if not letters or not letters.isalpha() or not letters.islower():
        raise ValueError("英小文字列が必要です")

    chars = list(letters)
    index = len(chars) - 1
    while index >= 0:
        if chars[index] != "z":
            chars[index] = chr(ord(chars[index]) + 1)
            return "".join(chars)
        chars[index] = "a"
        index -= 1
    return "a" + "".join(chars)


def next_sibling_id(current_id: str) -> str:
    """末尾の数字または英字列を1つ進める。"""
    match = re.search(r"([a-z]+|\d+)$", current_id)
    if not match:
        raise ValueError("IDの末尾を判定できません")
    tail = match.group(1)
    if tail.isdigit():
        replacement = str(int(tail) + 1)
    else:
        replacement = increment_letters(tail)
    return current_id[: match.start(1)] + replacement


def child_id(current_id: str) -> str:
    """末尾が数字ならa、英字なら1を追加する。"""
    if not current_id:
        raise ValueError("基準IDがありません")
    return current_id + ("a" if current_id[-1].isdigit() else "1")


def normalize_id(raw: str) -> str:
    """全角英数字を半角化し、英字を小文字へ統一する。"""
    return unicodedata.normalize("NFKC", raw).strip().lower()


def normalize_component(raw: str, lowercase: bool = False) -> str:
    """ファイル名の一部分を整える。日本語の波ダッシュはそのまま保持する。"""
    protected = raw.replace("～", "\ue000").replace("〜", "\ue001")
    value = unicodedata.normalize("NFKC", protected).strip()
    value = value.replace("\ue000", "～").replace("\ue001", "〜")
    if lowercase:
        value = value.lower()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip(" ._")


def normalize_title(raw: str) -> str:
    """トピック名は従来どおり英字を小文字へ統一する。"""
    return normalize_component(raw, lowercase=True)


def date_parts_in_name(value: str) -> Optional[tuple[str, str, str]]:
    """文字列中の有効なYYYY-MM-DDを取得する。後ろに文字が続いていてもよい。"""
    for match in DATE_IN_NAME_RE.finditer(value):
        year, month, day = match.group("year", "month", "day")
        try:
            datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
        except ValueError:
            continue
        return year, month, day
    return None


def split_id_tokens(folgezettel_id: str) -> list[str]:
    return re.findall(r"\d+|[a-z]+", folgezettel_id)


def parent_id(folgezettel_id: str) -> Optional[str]:
    """1a→1、1a1→1a。先頭の数字だけなら親なし。"""
    tokens = split_id_tokens(folgezettel_id)
    if len(tokens) <= 1:
        return None
    return "".join(tokens[:-1])


def is_direct_child(parent: str, candidate: str) -> bool:
    return parent_id(candidate) == parent


def parse_zettel_image(path: Path, prefix: str) -> Optional[dict]:
    """接頭辞付き画像名を通常・トピック・Index・その他ノートとして解析する。"""
    stem = path.stem
    if not stem.startswith(prefix):
        return None
    remainder = stem[len(prefix):]
    if not remainder:
        return None

    # ZK_Index_あ～い
    index_match = re.fullmatch(r"Index_(.+)", remainder, flags=re.IGNORECASE)
    if index_match:
        label = index_match.group(1)
        return {
            "kind": "range_index",
            "path": path,
            "stem": stem,
            "display_name": remainder,
            "label": label,
            "md_path": path.with_suffix(".md"),
        }

    # ZK_1 / ZK_2_bukkyou
    numeric_match = re.fullmatch(rf"({FOLGEZETTEL_ID_RE})(?:_(.+))?", remainder)
    if numeric_match:
        return {
            "kind": "numeric",
            "path": path,
            "stem": stem,
            "display_name": remainder,
            "id": numeric_match.group(1),
            "title": numeric_match.group(2),
            "is_topic": bool(numeric_match.group(2)),
            "md_path": path.with_suffix(".md"),
        }

    # ZK_diary_2026-07-31-FR / ZK_dream_...
    if "_" in remainder:
        category, name = remainder.split("_", 1)
        if category and name:
            date_parts = date_parts_in_name(name)
            return {
                "kind": "other",
                "path": path,
                "stem": stem,
                "display_name": remainder,
                "category": category,
                "other_name": name,
                "date_parts": date_parts,
                "md_path": path.with_suffix(".md"),
            }
    return None


def markdown_link(label: str, filename: str) -> str:
    return f"[{label}]({filename})"


def _parse_image_datetime(value: object) -> Optional[datetime]:
    """EXIF日時をdatetimeへ変換する。"""
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="ignore")
        except Exception:
            return None
    text = str(value).strip().strip("\x00")
    if not text:
        return None
    for fmt in (
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y:%m:%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def image_datetime(path: Path) -> datetime:
    """画像の撮影日時を返す。EXIF→Windows作成日時→更新日時の順。"""
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            # DateTimeOriginal, DateTimeDigitized, DateTime
            for tag in (36867, 36868, 306):
                parsed = _parse_image_datetime(exif.get(tag))
                if parsed is not None:
                    return parsed
    except Exception:
        pass

    try:
        stat = path.stat()
        if os.name == "nt" and stat.st_ctime > 0:
            return datetime.fromtimestamp(stat.st_ctime)
        birthtime = getattr(stat, "st_birthtime", None)
        if birthtime:
            return datetime.fromtimestamp(birthtime)
        return datetime.fromtimestamp(stat.st_mtime)
    except OSError:
        return datetime.now()


def _frontmatter_value(value: str) -> str:
    """通常のファイル名はそのまま、YAMLで危険な場合だけ引用する。"""
    if (
        not value
        or value[0] in "-?:,[]{}#&*!|>'\"%@`"
        or value != value.strip()
        or ": " in value
        or " #" in value
    ):
        return json.dumps(value, ensure_ascii=False)
    return value


def update_frontmatter(
    text: str,
    title: str,
    time_value: Optional[datetime] = None,
) -> str:
    """titleをファイル名へ更新し、指定時はtimeも更新する。その他のYAML項目は保持。"""
    normalized = text.replace("\r\n", "\n")
    lines = normalized.splitlines()
    body_start = 0
    existing: list[str] = []

    if lines and lines[0].strip() == "---":
        end_index = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_index = i
                break
        if end_index is not None:
            existing = lines[1:end_index]
            body_start = end_index + 1

    kept = [
        line
        for line in existing
        if not re.match(r"^\s*(?:time|title)\s*:", line, flags=re.IGNORECASE)
    ]

    if time_value is None:
        old_time = next(
            (line for line in existing if re.match(r"^\s*time\s*:", line, flags=re.IGNORECASE)),
            None,
        )
        time_line = old_time or f"time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    else:
        time_line = f"time: {time_value.strftime('%Y-%m-%d %H:%M:%S')}"

    frontmatter = [
        "---",
        time_line,
        f"title: {_frontmatter_value(title)}",
        *kept,
        "---",
    ]

    body = lines[body_start:] if body_start else lines
    while body and not body[0].strip():
        body.pop(0)
    result = "\n".join(frontmatter) + "\n\n" + "\n".join(body)
    if normalized.endswith("\n") or not body:
        result += "\n"
    return result


def managed_block(start: str, end: str, lines: list[str]) -> str:
    body = "\n".join(lines)
    if body:
        return f"{start}\n{body}\n{end}"
    return f"{start}\n{end}"


def _trim_blank_lines(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    cleaned: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        cleaned.append(line.rstrip())
        previous_blank = blank
    return cleaned


def _line_has_prefixed_link(line: str, prefix: str) -> bool:
    """MarkdownリンクまたはWikiリンクが指定接頭辞のノートを指すか判定する。"""
    for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", line):
        target = target.strip().strip("<>")
        target = target.split("#", 1)[0].split("?", 1)[0]
        filename = target.replace("\\", "/").rsplit("/", 1)[-1]
        root_name = prefix.rstrip("_-. ") or prefix
        if filename.startswith(prefix) or filename == f"{root_name}.md":
            return True

    for target in re.findall(r"\[\[([^\]|#]+)", line):
        filename = target.strip().replace("\\", "/").rsplit("/", 1)[-1]
        root_name = prefix.rstrip("_-. ") or prefix
        if filename.startswith(prefix) or filename == root_name:
            return True
    return False


def _remove_managed_block(text: str, start_marker: str, end_marker: str) -> str:
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        flags=re.DOTALL,
    )
    return pattern.sub("", text)


def _remove_legacy_marker_lines(text: str) -> str:
    """旧版が出力した管理用HTMLコメント行を削除する。"""
    markers = {
        MD_PARENT_START,
        MD_PARENT_END,
        MD_CHILD_START,
        MD_CHILD_END,
        MD_BACKLINK_START,
        MD_BACKLINK_END,
    }
    lines = [line for line in text.splitlines() if line.strip() not in markers]
    result = "\n".join(lines)
    if text.endswith("\n"):
        result += "\n"
    return result


def _section_match(text: str, label: str, next_label: Optional[str]):
    """見出し行から次の見出し直前までを取得する。"""
    if next_label:
        pattern = re.compile(
            rf"(?ms)^(?P<label>{re.escape(label)}[ \t]*)\n(?P<body>.*?)(?=^{re.escape(next_label)}[ \t]*$)"
        )
    else:
        pattern = re.compile(
            rf"(?ms)^(?P<label>{re.escape(label)}[ \t]*)\n(?P<body>.*?)\Z"
        )
    return pattern.search(text)


def _clean_section_lines(body: str, prefix: str) -> list[str]:
    """旧管理行とZKリンクを除き、手書き内容だけを残す。"""
    body = _remove_managed_block(body, MD_PARENT_START, MD_PARENT_END)
    body = _remove_managed_block(body, MD_CHILD_START, MD_CHILD_END)
    cleaned: list[str] = []
    legacy_markers = {
        MD_PARENT_START,
        MD_PARENT_END,
        MD_CHILD_START,
        MD_CHILD_END,
        "ZK関連",
        "ZK関連:",
        "その他",
        "その他:",
    }
    for line in body.splitlines():
        if line.strip() in legacy_markers:
            continue
        if _line_has_prefixed_link(line, prefix):
            continue
        cleaned.append(line)
    return _trim_blank_lines(cleaned)


def replace_parent_section(text: str, parent_lines: list[str], prefix: str) -> str:
    """自動生成するZK親リンクを更新し、その他のParent内容はそのまま残す。"""
    match = _section_match(text, "Parent:", "Child:")
    if match:
        remaining = _clean_section_lines(match.group("body"), prefix)
        combined = _trim_blank_lines(list(parent_lines) + remaining)
        replacement = "Parent:\n"
        if combined:
            replacement += "\n".join(combined) + "\n"
        # Child:の直前には空行を入れない。
        return text[:match.start()] + replacement + text[match.end():]

    suffix = "" if text.endswith("\n") else "\n"
    replacement = "\nParent:\n"
    if parent_lines:
        replacement += "\n".join(parent_lines) + "\n"
    return text + suffix + replacement


def replace_child_section(text: str, child_lines: list[str], prefix: str) -> str:
    """自動生成ZKリンクを更新し、見出しを付けずに手書き内容も保持する。"""
    match = _section_match(text, "Child:", "BackLink:")
    existing_body = match.group("body") if match else ""
    remaining = _clean_section_lines(existing_body, prefix)
    generated = _trim_blank_lines(list(child_lines))

    body_lines: list[str] = list(generated)
    if generated and remaining:
        body_lines.append("")
    body_lines.extend(remaining)
    body_lines = _trim_blank_lines(body_lines)

    # Child:の直後には空行を入れない。最後のリンクとBackLink:の間も空けない。
    replacement = "Child:\n"
    if body_lines:
        replacement += "\n".join(body_lines) + "\n"

    if match:
        result = text[:match.start()] + replacement + text[match.end():]
    else:
        backlink_match = re.search(r"(?m)^BackLink:[ \t]*$", text)
        if backlink_match:
            prefix_text = text[:backlink_match.start()]
            suffix = "" if prefix_text.endswith("\n") else "\n"
            result = prefix_text + suffix + replacement + text[backlink_match.start():]
        else:
            suffix = "" if text.endswith("\n") else "\n"
            result = text + suffix + "\n" + replacement

    # v4〜v6などで残ったBackLink用を含む管理コメントも削除する。
    return _remove_legacy_marker_lines(result)


def _relationship_sections(parent_lines: list[str], child_lines: list[str]) -> str:
    parent_body = "\n".join(_trim_blank_lines(list(parent_lines)))
    child_body = "\n".join(_trim_blank_lines(list(child_lines)))

    result = "Parent:\n"
    if parent_body:
        result += parent_body + "\n"
    result += "Child:\n"
    if child_body:
        result += child_body + "\n"
    result += "BackLink:\n"
    return result


def new_markdown_text(note: dict, prefix: str, parent_line: list[str], child_lines: list[str]) -> str:
    timestamp = image_datetime(note["path"]).strftime("%Y-%m-%d %H:%M:%S")
    title_value = note["path"].stem
    return (
        "---\n"
        f"time: {timestamp}\n"
        f"title: {_frontmatter_value(title_value)}\n"
        "---\n\n"
        f"# {note['display_name']}\n\n"
        f"![]({note['path'].name})\n\n"
        f"{_relationship_sections(parent_line, child_lines)}\n"
        "[Index](index.md)\n"
    )

def prefix_root_name(prefix: str) -> str:
    """ZK_ から ZK を得る。末尾区切りが複数あっても除く。"""
    root = prefix.rstrip("_-. ")
    return root or prefix or "ZK"


def read_markdown(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def new_index_markdown_text(
    path: Path,
    heading: str,
    parent_lines: list[str],
    child_lines: list[str],
) -> str:
    """画像を持たないZK索引ページ用テンプレート。"""
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    return (
        "---\n"
        f"time: {timestamp}\n"
        f"title: {_frontmatter_value(path.stem)}\n"
        "---\n\n"
        f"# {heading}\n\n"
        f"{_relationship_sections(parent_lines, child_lines)}\n"
        "[Index](index.md)\n"
    )

def topic_index_filename(prefix: str, folgezettel_id: str) -> str:
    return f"{prefix}{folgezettel_id}_Index.md"


def find_numeric_topic_indexes(folder: Path, prefix: str) -> dict[str, Path]:
    """ZK_2_Index.md のような既存の番号別Indexを取得する。"""
    pattern = re.compile(
        rf"^{re.escape(prefix)}(?P<id>{FOLGEZETTEL_ID_RE})_Index$",
        flags=re.IGNORECASE,
    )
    found: dict[str, Path] = {}
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() != ".md":
            continue
        match = pattern.fullmatch(path.stem)
        if match:
            found[normalize_id(match.group("id"))] = path
    return found


def find_range_index_files(folder: Path, prefix: str) -> list[tuple[str, Path]]:
    """ZK_Index_あ～い.md のようなユーザー作成索引を取得する。"""
    base = prefix_root_name(prefix)
    marker = f"{base}_Index_"
    result: list[tuple[str, Path]] = []
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() != ".md":
            continue
        stem = path.stem
        if stem.casefold().startswith(marker.casefold()) and len(stem) > len(marker):
            label = stem[len(marker):]
            result.append((label, path))
    result.sort(key=lambda item: natural_key(item[0]))
    return result


def update_or_create_index_markdown(
    path: Path,
    heading: str,
    parent_lines: list[str],
    child_lines: list[str],
    prefix: str,
    create_missing: bool,
) -> tuple[Optional[str], Optional[str]]:
    """戻り値は(old_content, new_content)。変更不要・未作成なら(None, None)。"""
    if path.exists():
        old_content = read_markdown(path)
        new_content = update_frontmatter(old_content, path.stem)
        new_content = replace_parent_section(new_content, parent_lines, prefix)
        new_content = replace_child_section(new_content, child_lines, prefix)
    elif create_missing:
        old_content = None
        new_content = new_index_markdown_text(path, heading, parent_lines, child_lines)
    else:
        return None, None
    if new_content == old_content:
        return None, None
    return old_content, new_content


def sync_markdown_folder(folder: Path, prefix: str, create_missing: bool = True) -> tuple[list[dict], dict]:
    """画像Markdown、番号Index、全体Index、その他カテゴリの年月Indexを同期する。"""
    parsed_images: list[dict] = []
    for path in folder.iterdir():
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            parsed = parse_zettel_image(path, prefix)
            if parsed:
                parsed_images.append(parsed)

    numeric_notes = [note for note in parsed_images if note["kind"] == "numeric"]
    range_index_notes = [note for note in parsed_images if note["kind"] == "range_index"]
    other_notes = [note for note in parsed_images if note["kind"] == "other"]

    regular_by_id = {note["id"]: note for note in numeric_notes if not note["is_topic"]}
    topics_by_id: dict[str, list[dict]] = {}
    for note in numeric_notes:
        if note["is_topic"]:
            topics_by_id.setdefault(note["id"], []).append(note)
    for topic_notes in topics_by_id.values():
        topic_notes.sort(key=lambda n: natural_key(n["path"].name))

    children_by_id: dict[str, list[dict]] = {}
    for note in regular_by_id.values():
        pid = parent_id(note["id"])
        if pid:
            children_by_id.setdefault(pid, []).append(note)
    for children in children_by_id.values():
        children.sort(key=lambda n: natural_key(n["id"]))

    numeric_indexes = find_numeric_topic_indexes(folder, prefix)
    for folgezettel_id in topics_by_id:
        numeric_indexes.setdefault(
            folgezettel_id,
            folder / topic_index_filename(prefix, folgezettel_id),
        )

    base = prefix_root_name(prefix)
    root_path = folder / f"{base}.md"
    global_index_path = folder / f"{base}_Index.md"

    changes: list[dict] = []
    created = 0
    updated = 0
    skipped = 0
    managed_files = 0

    def record_write(md_path: Path, old_content: Optional[str], new_content: str) -> None:
        nonlocal created, updated, managed_files
        managed_files += 1
        if new_content == old_content:
            return
        changes.append({"name": md_path.name, "old_content": old_content})
        md_path.write_text(new_content, encoding="utf-8")
        if old_content is None:
            created += 1
        else:
            updated += 1

    def root_parent_line() -> list[str]:
        return [markdown_link(base, root_path.name)]

    def write_image_note(note: dict, parent_lines: list[str], child_lines: list[str]) -> None:
        nonlocal skipped, managed_files
        md_path: Path = note["md_path"]
        if md_path.exists():
            old_content: Optional[str] = read_markdown(md_path)
            new_content = update_frontmatter(
                old_content,
                md_path.stem,
                image_datetime(note["path"]),
            )
            new_content = replace_parent_section(new_content, parent_lines, prefix)
            new_content = replace_child_section(new_content, child_lines, prefix)
        elif create_missing:
            old_content = None
            new_content = new_markdown_text(note, prefix, parent_lines, child_lines)
        else:
            skipped += 1
            return
        if new_content != old_content:
            record_write(md_path, old_content, new_content)
        else:
            managed_files += 1

    # 通常ノートとトピックノート。
    for note in sorted(numeric_notes, key=lambda n: natural_key(n["path"].name)):
        folgezettel_id = note["id"]
        index_path = numeric_indexes.get(folgezettel_id)
        if index_path is not None:
            parent_lines = [markdown_link(f"{folgezettel_id}_Index", index_path.name)]
        else:
            pid = parent_id(folgezettel_id)
            if pid:
                parent_lines = [markdown_link(pid, f"{prefix}{pid}.md")]
            else:
                parent_lines = root_parent_line()

        child_lines = (
            [
                markdown_link(child["id"], child["md_path"].name)
                for child in children_by_id.get(folgezettel_id, [])
            ]
            if not note["is_topic"]
            else []
        )
        write_image_note(note, parent_lines, child_lines)

    # 番号別トピックIndex。
    for folgezettel_id, index_path in sorted(
        numeric_indexes.items(), key=lambda item: natural_key(item[0])
    ):
        index_children: list[str] = []
        base_note = regular_by_id.get(folgezettel_id)
        if base_note:
            index_children.append(markdown_link(folgezettel_id, base_note["md_path"].name))
        index_children.extend(
            markdown_link(topic["display_name"], topic["md_path"].name)
            for topic in topics_by_id.get(folgezettel_id, [])
        )

        pid = parent_id(folgezettel_id)
        if pid:
            index_parent = [markdown_link(pid, f"{prefix}{pid}.md")]
        else:
            index_parent = root_parent_line()

        old_content, new_content = update_or_create_index_markdown(
            index_path,
            f"{folgezettel_id}_Index",
            index_parent,
            index_children,
            prefix,
            create_missing,
        )
        if new_content is not None:
            record_write(index_path, old_content, new_content)
        elif index_path.exists():
            managed_files += 1

    # Iキーで作る画像付き範囲Indexと、以前から存在するMarkdownだけの範囲Index。
    range_by_label: dict[str, dict] = {note["label"]: note for note in range_index_notes}
    existing_ranges = {label: path for label, path in find_range_index_files(folder, prefix)}
    all_range_labels = sorted(set(range_by_label) | set(existing_ranges), key=natural_key)
    range_entries: list[tuple[str, Path]] = []
    for label in all_range_labels:
        image_note = range_by_label.get(label)
        if image_note:
            write_image_note(
                image_note,
                [markdown_link("Index", global_index_path.name)],
                [],
            )
            range_path = image_note["md_path"]
        else:
            range_path = existing_ranges[label]
            old_content = read_markdown(range_path)
            new_content = update_frontmatter(old_content, range_path.stem)
            new_content = replace_parent_section(
                new_content,
                [markdown_link("Index", global_index_path.name)],
                prefix,
            )
            new_content = replace_child_section(new_content, [], prefix)
            if new_content != old_content:
                record_write(range_path, old_content, new_content)
            else:
                managed_files += 1
        range_entries.append((label, range_path))

    # Oモードのノートを category → year → month → image note の順に構成する。
    other_categories: dict[str, list[dict]] = {}
    for note in other_notes:
        other_categories.setdefault(note["category"], []).append(note)
    for category_notes in other_categories.values():
        category_notes.sort(key=lambda n: natural_key(n["other_name"]))

    other_root_links: list[str] = []
    for category in sorted(other_categories, key=natural_key):
        category_notes = other_categories[category]
        category_path = folder / f"{prefix}{category}.md"
        other_root_links.append(markdown_link(category, category_path.name))

        dated: dict[str, dict[str, list[dict]]] = {}
        undated: list[dict] = []
        for note in category_notes:
            parts = note.get("date_parts")
            if parts:
                year, month, _day = parts
                dated.setdefault(year, {}).setdefault(month, []).append(note)
            else:
                undated.append(note)

        multiple_years = len(dated) > 1

        # 実画像ノート。日付ありは月Index、日付なしはカテゴリ直下。
        for note in category_notes:
            parts = note.get("date_parts")
            if parts:
                year, month, _day = parts
                month_path = folder / f"{prefix}{category}_{year}-{month}.md"
                parent_lines = [markdown_link(f"{year}-{month}", month_path.name)]
            else:
                parent_lines = [markdown_link(category, category_path.name)]
            write_image_note(note, parent_lines, [])

        # 月Index。
        for year in sorted(dated, key=natural_key):
            for month in sorted(dated[year], key=natural_key):
                month_path = folder / f"{prefix}{category}_{year}-{month}.md"
                year_path = folder / f"{prefix}{category}_{year}.md"
                month_children = [
                    markdown_link(note["other_name"], note["md_path"].name)
                    for note in sorted(dated[year][month], key=lambda n: natural_key(n["other_name"]))
                ]
                month_parent = (
                    [markdown_link(year, year_path.name)]
                    if multiple_years
                    else [markdown_link(category, category_path.name)]
                )
                old_content, new_content = update_or_create_index_markdown(
                    month_path,
                    f"{category}_{year}-{month}",
                    month_parent,
                    month_children,
                    prefix,
                    create_missing,
                )
                if new_content is not None:
                    record_write(month_path, old_content, new_content)
                elif month_path.exists():
                    managed_files += 1

        # 複数年にまたがる場合だけ年Indexを作る。
        if multiple_years:
            for year in sorted(dated, key=natural_key):
                year_path = folder / f"{prefix}{category}_{year}.md"
                year_children = [
                    markdown_link(
                        f"{year}-{month}",
                        f"{prefix}{category}_{year}-{month}.md",
                    )
                    for month in sorted(dated[year], key=natural_key)
                ]
                old_content, new_content = update_or_create_index_markdown(
                    year_path,
                    f"{category}_{year}",
                    [markdown_link(category, category_path.name)],
                    year_children,
                    prefix,
                    create_missing,
                )
                if new_content is not None:
                    record_write(year_path, old_content, new_content)
                elif year_path.exists():
                    managed_files += 1

        # 1年だけなら月を直下へ、複数年なら年を直下へ置く。
        if multiple_years:
            category_children = [
                markdown_link(year, f"{prefix}{category}_{year}.md")
                for year in sorted(dated, key=natural_key)
            ]
        else:
            category_children = []
            for year in sorted(dated, key=natural_key):
                category_children.extend(
                    markdown_link(
                        f"{year}-{month}",
                        f"{prefix}{category}_{year}-{month}.md",
                    )
                    for month in sorted(dated[year], key=natural_key)
                )
        if category_children and undated:
            category_children.append("")
        category_children.extend(
            markdown_link(note["other_name"], note["md_path"].name)
            for note in sorted(undated, key=lambda n: natural_key(n["other_name"]))
        )
        old_content, new_content = update_or_create_index_markdown(
            category_path,
            category,
            root_parent_line(),
            category_children,
            prefix,
            create_missing,
        )
        if new_content is not None:
            record_write(category_path, old_content, new_content)
        elif category_path.exists():
            managed_files += 1

    # ZK_Index.md。
    global_index_children = [
        markdown_link(label, path.name) for label, path in range_entries
    ]
    old_content, new_content = update_or_create_index_markdown(
        global_index_path,
        "Index",
        root_parent_line(),
        global_index_children,
        prefix,
        create_missing,
    )
    if new_content is not None:
        record_write(global_index_path, old_content, new_content)
    elif global_index_path.exists():
        managed_files += 1

    # ZK.md: Index → 空行 → Oカテゴリ → 空行 → 通常番号ノート。
    top_ids = {
        folgezettel_id
        for folgezettel_id in set(regular_by_id) | set(topics_by_id) | set(numeric_indexes)
        if parent_id(folgezettel_id) is None
    }
    numeric_root_links: list[str] = []
    for folgezettel_id in sorted(top_ids, key=natural_key):
        index_path = numeric_indexes.get(folgezettel_id)
        if index_path and index_path.exists():
            numeric_root_links.append(markdown_link(f"{folgezettel_id}_Index", index_path.name))
        elif folgezettel_id in regular_by_id:
            numeric_root_links.append(
                markdown_link(folgezettel_id, regular_by_id[folgezettel_id]["md_path"].name)
            )

    root_children: list[str] = [markdown_link("Index", global_index_path.name)]
    if other_root_links:
        root_children.append("")
        root_children.extend(other_root_links)
    if numeric_root_links:
        root_children.append("")
        root_children.extend(numeric_root_links)

    old_content, new_content = update_or_create_index_markdown(
        root_path,
        base,
        [],
        root_children,
        prefix,
        create_missing,
    )
    if new_content is not None:
        record_write(root_path, old_content, new_content)
    elif root_path.exists():
        managed_files += 1

    return changes, {
        "images": len(parsed_images),
        "managed_files": managed_files,
        "created": created,
        "updated": updated,
        "unchanged": max(0, managed_files - created - updated),
        "skipped": skipped,
    }


def restore_markdown_changes(folder: Path, changes: list[dict]) -> None:
    for change in reversed(changes):
        path = folder / change["name"]
        old_content = change.get("old_content")
        if old_content is None:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
        else:
            try:
                path.write_text(old_content, encoding="utf-8")
            except OSError:
                pass


@dataclass
class ImageItem:
    original_name: str
    current_name: str
    folgezettel_id: Optional[str] = None
    processed: bool = False
    topic_title: Optional[str] = None
    note_kind: Optional[str] = None
    index_label: Optional[str] = None
    other_category: Optional[str] = None
    other_name: Optional[str] = None

    def current_path(self, folder: Path) -> Path:
        return folder / self.current_name


class FolgezettelApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1280x820")
        self.root.minsize(980, 680)

        self.folder: Optional[Path] = None
        self.items: list[ImageItem] = []
        self.current_index = 0
        self.undo_stack: list[dict] = []
        self.drag_iid: Optional[str] = None
        self.thumbnail_refs: dict[str, ImageTk.PhotoImage] = {}

        self.prefix_var = tk.StringVar(value="ZK_")
        self.sort_var = tk.StringVar(value="ファイル名（自然順・昇順）")
        self.folder_var = tk.StringVar(value="フォルダ未選択")
        self.status_var = tk.StringVar(value="フォルダを選択してください")
        self.progress_var = tk.StringVar(value="")
        self.previous_id_var = tk.StringVar(value="なし")
        self.current_file_var = tk.StringVar(value="")
        self.input_var = tk.StringVar(value="")
        self.topic_id_var = tk.StringVar(value="")
        self.topic_title_var = tk.StringVar(value="")
        self.topic_preview_var = tk.StringVar(value="")
        self.index_label_var = tk.StringVar(value="")
        self.index_preview_var = tk.StringVar(value="")
        self.other_category_var = tk.StringVar(value="")
        self.other_name_var = tk.StringVar(value="")
        self.other_preview_var = tk.StringVar(value="")
        self.other_mode_active = False
        self.other_mode_category = ""
        self.auto_markdown_var = tk.BooleanVar(value=True)

        self.preview_image: Optional[ImageTk.PhotoImage] = None
        self.full_image: Optional[Image.Image] = None
        self.zoom = 1.0
        self.input_active = False

        self._build_setup_frame()
        self._build_naming_frame()
        self.show_setup()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- UI construction ----------
    def _build_setup_frame(self):
        self.setup_frame = ttk.Frame(self.root, padding=12)
        top = ttk.Frame(self.setup_frame)
        top.pack(fill="x")

        ttk.Button(top, text="画像フォルダを選択", command=self.choose_folder).pack(side="left")
        ttk.Label(top, textvariable=self.folder_var).pack(side="left", padx=10)

        ttk.Label(top, text="ファイル名の接頭辞:").pack(side="left", padx=(22, 4))
        prefix_entry = ttk.Entry(top, textvariable=self.prefix_var, width=15)
        prefix_entry.pack(side="left")
        ttk.Checkbutton(
            top, text="Markdownを自動作成", variable=self.auto_markdown_var
        ).pack(side="left", padx=(14, 0))

        ttk.Button(top, text="名前付けを開始", command=self.start_naming).pack(side="right")
        ttk.Button(top, text="Markdownを一括更新", command=self.update_markdown_existing).pack(
            side="right", padx=(0, 8)
        )

        controls = ttk.Frame(self.setup_frame)
        controls.pack(fill="x", pady=(12, 8))
        ttk.Label(controls, text="自動並び替え:").pack(side="left")
        sort_combo = ttk.Combobox(
            controls,
            textvariable=self.sort_var,
            state="readonly",
            width=28,
            values=[
                "ファイル名（自然順・昇順）",
                "ファイル名（自然順・降順）",
                "作成日時（古い順）",
                "作成日時（新しい順）",
                "更新日時（古い順）",
                "更新日時（新しい順）",
            ],
        )
        sort_combo.pack(side="left", padx=6)
        ttk.Button(controls, text="適用", command=self.apply_sort).pack(side="left")

        ttk.Separator(controls, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(controls, text="一つ上へ", command=lambda: self.move_selected(-1)).pack(side="left")
        ttk.Button(controls, text="一つ下へ", command=lambda: self.move_selected(1)).pack(side="left", padx=4)
        ttk.Button(controls, text="先頭へ", command=lambda: self.move_selected_to("top")).pack(side="left")
        ttk.Button(controls, text="末尾へ", command=lambda: self.move_selected_to("bottom")).pack(side="left", padx=4)
        ttk.Button(controls, text="選択画像を除外", command=self.exclude_selected).pack(side="left", padx=(12, 0))

        body = ttk.Panedwindow(self.setup_frame, orient="horizontal")
        body.pack(fill="both", expand=True)

        list_frame = ttk.Frame(body)
        preview_frame = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(list_frame, weight=3)
        body.add(preview_frame, weight=2)

        self.tree = ttk.Treeview(
            list_frame,
            columns=("order", "name", "modified", "size"),
            show="tree headings",
            selectmode="extended",
        )
        self.tree.heading("#0", text="画像")
        self.tree.heading("order", text="順番")
        self.tree.heading("name", text="ファイル名")
        self.tree.heading("modified", text="更新日時")
        self.tree.heading("size", text="サイズ")
        self.tree.column("#0", width=110, stretch=False)
        self.tree.column("order", width=60, anchor="center", stretch=False)
        self.tree.column("name", width=360)
        self.tree.column("modified", width=145, stretch=False)
        self.tree.column("size", width=90, anchor="e", stretch=False)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<ButtonPress-1>", self.on_drag_start, add=True)
        self.tree.bind("<B1-Motion>", self.on_drag_motion, add=True)
        self.tree.bind("<ButtonRelease-1>", self.on_drag_end, add=True)
        self.tree.bind("<Control-Up>", lambda e: self.move_selected(-1))
        self.tree.bind("<Control-Down>", lambda e: self.move_selected(1))
        self.tree.bind("<Control-Home>", lambda e: self.move_selected_to("top"))
        self.tree.bind("<Control-End>", lambda e: self.move_selected_to("bottom"))

        ttk.Label(preview_frame, text="選択画像の確認").pack(anchor="w")
        self.setup_preview = tk.Canvas(preview_frame, background="#333333", highlightthickness=0)
        self.setup_preview.pack(fill="both", expand=True, pady=(6, 0))
        ttk.Label(
            self.setup_frame,
            text="ドラッグ＆ドロップ、またはボタン／Ctrl＋上下キーで順番を変更できます。",
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(self.setup_frame, textvariable=self.status_var).pack(anchor="w", pady=(2, 0))

    def _build_naming_frame(self):
        self.naming_frame = ttk.Frame(self.root, padding=10)

        header = ttk.Frame(self.naming_frame)
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.progress_var, font=("Yu Gothic UI", 11, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.current_file_var).pack(side="left", padx=16)
        ttk.Label(header, text="直前のID:").pack(side="left", padx=(20, 4))
        ttk.Label(header, textvariable=self.previous_id_var, font=("Consolas", 11, "bold")).pack(side="left")
        ttk.Label(header, text="接頭辞:").pack(side="left", padx=(20, 4))
        ttk.Label(header, textvariable=self.prefix_var, font=("Consolas", 11)).pack(side="left")
        ttk.Button(header, text="保存して終了", command=self.on_close).pack(side="right")
        ttk.Button(header, text="Markdown更新", command=self.update_markdown_existing).pack(
            side="right", padx=(0, 8)
        )

        self.image_canvas = tk.Canvas(self.naming_frame, background="#202020", highlightthickness=0)
        self.image_canvas.pack(fill="both", expand=True, pady=8)
        self.image_canvas.bind("<Configure>", lambda e: self.render_current_image())
        self.image_canvas.bind("<MouseWheel>", self.on_mousewheel)

        self.input_frame = ttk.Frame(self.naming_frame)
        ttk.Label(self.input_frame, text="ID:").pack(side="left")
        self.input_entry = ttk.Entry(self.input_frame, textvariable=self.input_var, font=("Consolas", 16), width=28)
        self.input_entry.pack(side="left", padx=8)
        ttk.Label(self.input_frame, text="Enterで確定 / Escでキャンセル").pack(side="left")
        self.input_entry.bind("<Return>", self.confirm_manual_id)
        self.input_entry.bind("<Escape>", self.cancel_input)

        self.topic_frame = ttk.Frame(self.naming_frame)
        ttk.Label(self.topic_frame, text="番号:").pack(side="left")
        self.topic_id_entry = ttk.Entry(
            self.topic_frame, textvariable=self.topic_id_var, font=("Consolas", 16), width=12
        )
        self.topic_id_entry.pack(side="left", padx=(6, 14))
        ttk.Label(self.topic_frame, text="タイトル:").pack(side="left")
        self.topic_title_entry = ttk.Entry(
            self.topic_frame, textvariable=self.topic_title_var, font=("Consolas", 16), width=28
        )
        self.topic_title_entry.pack(side="left", padx=6)
        ttk.Label(self.topic_frame, textvariable=self.topic_preview_var).pack(side="left", padx=(10, 0))
        self.topic_id_entry.bind("<Return>", self.focus_topic_title)
        self.topic_title_entry.bind("<Return>", self.confirm_topic_note)
        self.topic_id_entry.bind("<Escape>", self.cancel_input)
        self.topic_title_entry.bind("<Escape>", self.cancel_input)
        self.topic_id_var.trace_add("write", self.update_topic_preview)
        self.topic_title_var.trace_add("write", self.update_topic_preview)

        self.index_frame = ttk.Frame(self.naming_frame)
        ttk.Label(self.index_frame, text="Index名:").pack(side="left")
        self.index_label_entry = ttk.Entry(
            self.index_frame, textvariable=self.index_label_var, font=("Consolas", 16), width=30
        )
        self.index_label_entry.pack(side="left", padx=8)
        ttk.Label(self.index_frame, textvariable=self.index_preview_var).pack(side="left", padx=(10, 0))
        self.index_label_entry.bind("<Return>", self.confirm_index_note)
        self.index_label_entry.bind("<Escape>", self.cancel_input)
        self.index_label_var.trace_add("write", self.update_index_preview)

        self.other_frame = ttk.Frame(self.naming_frame)
        ttk.Label(self.other_frame, text="分類:").pack(side="left")
        self.other_category_entry = ttk.Entry(
            self.other_frame, textvariable=self.other_category_var, font=("Consolas", 16), width=14
        )
        self.other_category_entry.pack(side="left", padx=(6, 14))
        ttk.Label(self.other_frame, text="名前:").pack(side="left")
        self.other_name_entry = ttk.Entry(
            self.other_frame, textvariable=self.other_name_var, font=("Consolas", 16), width=32
        )
        self.other_name_entry.pack(side="left", padx=6)
        ttk.Label(self.other_frame, textvariable=self.other_preview_var).pack(side="left", padx=(10, 0))
        self.other_category_entry.bind("<Return>", self.focus_other_name)
        self.other_name_entry.bind("<Return>", self.confirm_other_note)
        self.other_category_entry.bind("<KeyPress-O>", self.on_other_exit)
        self.other_name_entry.bind("<KeyPress-O>", self.on_other_exit)
        self.other_category_entry.bind("<Escape>", self.cancel_input)
        self.other_name_entry.bind("<Escape>", self.cancel_input)
        self.other_category_var.trace_add("write", self.update_other_preview)
        self.other_name_var.trace_add("write", self.update_other_preview)

        self.prefix_var.trace_add("write", self.update_topic_preview)
        self.prefix_var.trace_add("write", self.update_index_preview)
        self.prefix_var.trace_add("write", self.update_other_preview)

        help_text = (
            "通常: → 連番  ↓ 子ID  ↑ 直前IDを編集  Space 空欄入力  "
            "T トピック  I Index  o その他モード  O その他モード解除  ← 取り消し"
        )
        self.naming_help = ttk.Label(self.naming_frame, text=help_text)
        self.naming_help.pack(anchor="center")
        self.naming_status = ttk.Label(self.naming_frame, textvariable=self.status_var)
        self.naming_status.pack(anchor="center", pady=(3, 0))

    # ---------- folder and project ----------
    def choose_folder(self):
        selected = filedialog.askdirectory(title="画像フォルダを選択")
        if not selected:
            return
        self.load_folder(Path(selected))

    def load_folder(self, folder: Path):
        self.folder = folder
        self.folder_var.set(str(folder))
        project_path = folder / PROJECT_FILE

        loaded_project = False
        if project_path.exists():
            use_project = messagebox.askyesno(
                "前回の作業データ",
                "このフォルダには前回の作業データがあります。再開しますか？\n\n「いいえ」を選ぶと現在のファイルから新しく一覧を作ります。",
            )
            if use_project:
                loaded_project = self.load_project(project_path)

        if not loaded_project:
            paths = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
            paths.sort(key=lambda p: natural_key(p.name))
            self.items = [ImageItem(original_name=p.name, current_name=p.name) for p in paths]
            self.current_index = 0
            self.undo_stack.clear()

        self.refresh_tree()
        self.status_var.set(f"{len(self.items)}枚を読み込みました")

    def project_path(self) -> Optional[Path]:
        return self.folder / PROJECT_FILE if self.folder else None

    def save_project(self):
        if not self.folder:
            return
        data = {
            "version": 5,
            "folder": str(self.folder),
            "prefix": self.prefix_var.get(),
            "auto_markdown": self.auto_markdown_var.get(),
            "other_mode_active": self.other_mode_active,
            "other_mode_category": self.other_mode_category,
            "current_index": self.current_index,
            "items": [asdict(item) for item in self.items],
            "undo_stack": self.undo_stack,
        }
        try:
            self.project_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self.status_var.set(f"作業データを保存できませんでした: {exc}")

    def load_project(self, project_path: Path) -> bool:
        try:
            data = json.loads(project_path.read_text(encoding="utf-8"))
            items = [ImageItem(**item) for item in data.get("items", [])]
            # 実在しないファイルは除外せず警告対象として残す。まず1件でも存在するか確認。
            if not items:
                return False
            self.items = items
            self.prefix_var.set(data.get("prefix", "ZK_"))
            self.auto_markdown_var.set(bool(data.get("auto_markdown", True)))
            self.other_mode_active = bool(data.get("other_mode_active", False))
            self.other_mode_category = str(data.get("other_mode_category", ""))
            self.current_index = int(data.get("current_index", 0))
            self.undo_stack = data.get("undo_stack", [])
            return True
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            messagebox.showwarning("作業データを読み込めません", str(exc))
            return False

    # ---------- setup list ----------
    def refresh_tree(self):
        self.thumbnail_refs.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        if not self.folder:
            return

        for idx, item in enumerate(self.items):
            path = item.current_path(self.folder)
            stat_text = ""
            size_text = ""
            image_ref = None
            try:
                st = path.stat()
                import datetime as _dt
                stat_text = _dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                size_text = self.format_size(st.st_size)
                image_ref = self.make_thumbnail(path, (86, 66))
            except OSError:
                pass
            iid = str(idx)
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text="",
                image=image_ref,
                values=(idx + 1, item.current_name, stat_text, size_text),
            )
            if image_ref:
                self.thumbnail_refs[iid] = image_ref

    @staticmethod
    def format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        if size < 1024**2:
            return f"{size / 1024:.1f} KB"
        return f"{size / 1024**2:.1f} MB"

    def make_thumbnail(self, path: Path, size: tuple[int, int]) -> Optional[ImageTk.PhotoImage]:
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail(size, Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(image.copy())
        except Exception:
            return None

    def apply_sort(self):
        if not self.folder or not self.items:
            return
        mode = self.sort_var.get()

        def safe_stat(item: ImageItem, field: str):
            try:
                st = item.current_path(self.folder).stat()
                return getattr(st, field)
            except OSError:
                return 0

        if mode == "ファイル名（自然順・昇順）":
            self.items.sort(key=lambda i: natural_key(i.current_name))
        elif mode == "ファイル名（自然順・降順）":
            self.items.sort(key=lambda i: natural_key(i.current_name), reverse=True)
        elif mode == "作成日時（古い順）":
            self.items.sort(key=lambda i: safe_stat(i, "st_ctime"))
        elif mode == "作成日時（新しい順）":
            self.items.sort(key=lambda i: safe_stat(i, "st_ctime"), reverse=True)
        elif mode == "更新日時（古い順）":
            self.items.sort(key=lambda i: safe_stat(i, "st_mtime"))
        elif mode == "更新日時（新しい順）":
            self.items.sort(key=lambda i: safe_stat(i, "st_mtime"), reverse=True)
        self.current_index = self.first_unprocessed_index()
        self.refresh_tree()
        self.save_project()

    def selected_indices(self) -> list[int]:
        result = []
        for iid in self.tree.selection():
            try:
                result.append(int(iid))
            except ValueError:
                continue
        return sorted(result)

    def move_selected(self, delta: int):
        indices = self.selected_indices()
        if len(indices) != 1:
            self.status_var.set("一つの画像を選択してください")
            return "break"
        i = indices[0]
        j = i + delta
        if not (0 <= j < len(self.items)):
            return "break"
        self.items[i], self.items[j] = self.items[j], self.items[i]
        self.refresh_tree()
        self.tree.selection_set(str(j))
        self.tree.see(str(j))
        self.save_project()
        return "break"

    def move_selected_to(self, where: str):
        indices = self.selected_indices()
        if len(indices) != 1:
            self.status_var.set("一つの画像を選択してください")
            return "break"
        i = indices[0]
        item = self.items.pop(i)
        j = 0 if where == "top" else len(self.items)
        self.items.insert(j, item)
        self.refresh_tree()
        self.tree.selection_set(str(j))
        self.tree.see(str(j))
        self.save_project()
        return "break"

    def exclude_selected(self):
        indices = self.selected_indices()
        if not indices:
            return
        if any(self.items[i].processed for i in indices):
            messagebox.showwarning("除外できません", "名前付け済みの画像は除外できません。先に取り消してください。")
            return
        if not messagebox.askyesno("一覧から除外", f"選択した{len(indices)}枚を今回の作業一覧から除外しますか？\nファイル自体は削除しません。"):
            return
        for i in reversed(indices):
            self.items.pop(i)
        self.current_index = self.first_unprocessed_index()
        self.refresh_tree()
        self.save_project()

    def on_tree_select(self, _event=None):
        indices = self.selected_indices()
        if not indices or not self.folder:
            return
        path = self.items[indices[0]].current_path(self.folder)
        self.render_setup_preview(path)

    def render_setup_preview(self, path: Path):
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                width = max(self.setup_preview.winfo_width(), 400)
                height = max(self.setup_preview.winfo_height(), 300)
                image.thumbnail((width - 20, height - 20), Image.Resampling.LANCZOS)
                self.preview_image = ImageTk.PhotoImage(image.copy())
            self.setup_preview.delete("all")
            self.setup_preview.create_image(width // 2, height // 2, image=self.preview_image, anchor="center")
        except Exception as exc:
            self.setup_preview.delete("all")
            self.setup_preview.create_text(20, 20, text=f"画像を表示できません\n{exc}", anchor="nw", fill="white")

    def on_drag_start(self, event):
        self.drag_iid = self.tree.identify_row(event.y)

    def on_drag_motion(self, event):
        if not self.drag_iid:
            return
        target = self.tree.identify_row(event.y)
        if target and target != self.drag_iid:
            target_index = self.tree.index(target)
            self.tree.move(self.drag_iid, "", target_index)

    def on_drag_end(self, _event):
        if not self.drag_iid:
            return
        old_items = self.items[:]
        new_items = []
        for iid in self.tree.get_children():
            try:
                new_items.append(old_items[int(iid)])
            except (ValueError, IndexError):
                pass
        if len(new_items) == len(old_items):
            self.items = new_items
            self.refresh_tree()
            self.save_project()
        self.drag_iid = None

    # ---------- Markdown ----------
    def update_markdown_existing(self):
        dialog_options = {"title": "Markdownを更新するフォルダを選択"}
        if self.folder:
            dialog_options["initialdir"] = str(self.folder)
        selected = filedialog.askdirectory(**dialog_options)
        if not selected:
            return
        target = Path(selected)

        prefix = self.prefix_var.get()
        if not prefix:
            messagebox.showwarning("接頭辞が必要です", "ZK_などの接頭辞を入力してください。")
            return
        try:
            _changes, result = sync_markdown_folder(target, prefix, create_missing=True)
        except OSError as exc:
            messagebox.showerror("Markdownを更新できません", str(exc))
            return
        self.status_var.set(
            f"Markdown更新完了: 新規{result['created']}、更新{result['updated']}、管理対象{result['managed_files']}"
        )
        messagebox.showinfo(
            "Markdown更新完了",
            f"対象画像: {result['images']}\n"
            f"管理対象Markdown: {result['managed_files']}\n"
            f"新規作成: {result['created']}\n"
            f"更新: {result['updated']}\n"
            f"変更なし: {result['unchanged']}",
        )

    def sync_markdown_after_commit(self) -> list[dict]:
        auto_var = getattr(self, "auto_markdown_var", None)
        if not self.folder or auto_var is None or not auto_var.get():
            return []
        try:
            changes, result = sync_markdown_folder(self.folder, self.prefix_var.get(), create_missing=True)
            self.status_var.set(
                f"Markdown: 新規{result['created']}、更新{result['updated']}"
            )
            return changes
        except OSError as exc:
            messagebox.showwarning(
                "Markdownを作成できません",
                f"画像のファイル名は変更しましたが、Markdown処理に失敗しました。\n\n{exc}",
            )
            return []

    # ---------- naming ----------
    def show_setup(self):
        self.unbind_naming_keys()
        self.naming_frame.pack_forget()
        self.setup_frame.pack(fill="both", expand=True)

    def start_naming(self):
        if not self.folder or not self.items:
            messagebox.showwarning("画像がありません", "先に画像フォルダを選択してください。")
            return
        prefix = self.prefix_var.get()
        if any(ch in INVALID_WINDOWS_CHARS for ch in prefix):
            messagebox.showerror("接頭辞が不正です", '接頭辞には次の文字を使用できません。\n< > : " / \\ | ? *')
            return
        self.current_index = self.first_unprocessed_index()
        if self.current_index >= len(self.items):
            messagebox.showinfo("完了", "すべての画像に名前が付いています。")
            return
        self.setup_frame.pack_forget()
        self.naming_frame.pack(fill="both", expand=True)
        self.input_active = False
        self.hide_input()
        self.bind_naming_keys()
        self.load_current_image()

    def first_unprocessed_index(self) -> int:
        for i, item in enumerate(self.items):
            if not item.processed:
                return i
        return len(self.items)

    def bind_naming_keys(self):
        self.root.bind("<Right>", self.on_right)
        self.root.bind("<Down>", self.on_down)
        self.root.bind("<Up>", self.on_up)
        self.root.bind("<Left>", self.on_left)
        self.root.bind("<space>", self.on_space)
        self.root.bind("<KeyPress-t>", self.on_topic)
        self.root.bind("<KeyPress-T>", self.on_topic)
        self.root.bind("<KeyPress-i>", self.on_index)
        self.root.bind("<KeyPress-I>", self.on_index)
        self.root.bind("<KeyPress-o>", self.on_other_start)
        self.root.bind("<KeyPress-O>", self.on_other_exit)
        self.root.bind("<Escape>", self.on_escape_global)

    def unbind_naming_keys(self):
        for sequence in (
            "<Right>", "<Down>", "<Up>", "<Left>", "<space>",
            "<KeyPress-t>", "<KeyPress-T>",
            "<KeyPress-i>", "<KeyPress-I>",
            "<KeyPress-o>", "<KeyPress-O>",
            "<Escape>",
        ):
            self.root.unbind(sequence)

    def previous_id(self) -> Optional[str]:
        if self.current_index <= 0:
            return None
        for i in range(self.current_index - 1, -1, -1):
            if self.items[i].processed and self.items[i].folgezettel_id:
                return self.items[i].folgezettel_id
        return None

    def load_current_image(self):
        if not self.folder:
            return
        if self.current_index >= len(self.items):
            self.finish_work()
            return
        item = self.items[self.current_index]
        path = item.current_path(self.folder)
        self.progress_var.set(f"画像 {self.current_index + 1} / {len(self.items)}")
        self.current_file_var.set(f"元: {item.original_name}　現在: {item.current_name}")
        self.previous_id_var.set(self.previous_id() or "なし")
        self.status_var.set("画像内のIDを確認してください")
        self.zoom = 1.0
        try:
            with Image.open(path) as image:
                self.full_image = ImageOps.exif_transpose(image).convert("RGB")
            self.render_current_image()
        except Exception as exc:
            self.full_image = None
            self.image_canvas.delete("all")
            self.image_canvas.create_text(20, 20, text=f"画像を表示できません\n{exc}", anchor="nw", fill="white")

        if self.other_mode_active and not self.input_active:
            category = self.other_mode_category
            self.root.after_idle(lambda: self.show_other_input(category))

    def render_current_image(self):
        if self.full_image is None:
            return
        canvas_w = max(self.image_canvas.winfo_width(), 200)
        canvas_h = max(self.image_canvas.winfo_height(), 200)
        fit = min((canvas_w - 20) / self.full_image.width, (canvas_h - 20) / self.full_image.height)
        scale = max(0.05, fit * self.zoom)
        width = max(1, int(self.full_image.width * scale))
        height = max(1, int(self.full_image.height * scale))
        displayed = self.full_image.resize((width, height), Image.Resampling.LANCZOS)
        self.preview_image = ImageTk.PhotoImage(displayed)
        self.image_canvas.delete("all")
        self.image_canvas.create_image(canvas_w // 2, canvas_h // 2, image=self.preview_image, anchor="center")

    def on_mousewheel(self, event):
        # Ctrlの有無にかかわらず名前付け画面では拡大縮小に使う。
        if event.delta > 0:
            self.zoom = min(8.0, self.zoom * 1.15)
        else:
            self.zoom = max(0.2, self.zoom / 1.15)
        self.render_current_image()

    def on_right(self, _event=None):
        if self.input_active:
            return
        previous = self.previous_id()
        if previous is None:
            self.status_var.set("最初の画像はSpaceキーでIDを入力してください")
            return "break"
        try:
            self.commit_id(next_sibling_id(previous))
        except ValueError as exc:
            self.status_var.set(str(exc))
        return "break"

    def on_down(self, _event=None):
        if self.input_active:
            return
        previous = self.previous_id()
        if previous is None:
            self.status_var.set("最初の画像はSpaceキーでIDを入力してください")
            return "break"
        try:
            self.commit_id(child_id(previous))
        except ValueError as exc:
            self.status_var.set(str(exc))
        return "break"

    def on_up(self, _event=None):
        if self.input_active:
            return
        self.show_input(self.previous_id() or "")
        return "break"

    def on_space(self, _event=None):
        if self.input_active:
            return
        self.show_input("")
        return "break"

    def on_topic(self, _event=None):
        if self.input_active:
            return "break"
        self.show_topic_input(self.previous_id() or "")
        return "break"

    def on_index(self, _event=None):
        if self.input_active:
            return "break"
        self.show_index_input()
        return "break"

    def on_other_start(self, _event=None):
        if self.input_active:
            return "break"
        self.other_mode_active = True
        self.other_mode_category = ""
        self.show_other_input("")
        self.save_project()
        return "break"

    def on_other_exit(self, _event=None):
        if not self.other_mode_active and not self.other_frame.winfo_ismapped():
            return "break"
        self.other_mode_active = False
        self.other_mode_category = ""
        self.hide_input()
        self.status_var.set("その他モードを解除しました")
        self.save_project()
        return "break"

    def on_left(self, _event=None):
        if self.input_active:
            return
        self.undo_last()
        return "break"

    def on_escape_global(self, _event=None):
        if self.input_active:
            self.cancel_input()
        return "break"

    def show_input(self, value: str):
        self.topic_frame.pack_forget()
        self.index_frame.pack_forget()
        self.other_frame.pack_forget()
        self.input_active = True
        self.input_var.set(value)
        self.input_frame.pack(before=self.naming_help, pady=(0, 8))
        self.input_entry.focus_set()
        self.input_entry.icursor(tk.END)
        self.status_var.set("IDを入力または修正してEnterで確定します")

    def show_topic_input(self, value: str):
        self.input_frame.pack_forget()
        self.index_frame.pack_forget()
        self.other_frame.pack_forget()
        self.input_active = True
        self.topic_id_var.set(value)
        self.topic_title_var.set("")
        self.update_topic_preview()
        self.topic_frame.pack(before=self.naming_help, pady=(0, 8))
        self.topic_id_entry.focus_set()
        self.topic_id_entry.selection_range(0, tk.END)
        self.status_var.set("番号を入力し、TabまたはEnterでタイトル欄へ移動します")

    def show_index_input(self):
        self.input_frame.pack_forget()
        self.topic_frame.pack_forget()
        self.other_frame.pack_forget()
        self.input_active = True
        self.index_label_var.set("")
        self.update_index_preview()
        self.index_frame.pack(before=self.naming_help, pady=(0, 8))
        self.index_label_entry.focus_set()
        self.status_var.set("Index名を入力してください（例: あ～い）")

    def show_other_input(self, category: str):
        self.input_frame.pack_forget()
        self.topic_frame.pack_forget()
        self.index_frame.pack_forget()
        self.input_active = True
        self.other_category_var.set(category)
        self.other_name_var.set("")
        self.update_other_preview()
        self.other_frame.pack(before=self.naming_help, pady=(0, 8))
        if category:
            self.other_name_entry.focus_set()
            self.status_var.set(f"その他モード「{category}」: 名前を入力してEnterで確定します")
        else:
            self.other_category_entry.focus_set()
            self.status_var.set("分類名を入力し、TabまたはEnterで名前欄へ移動します")

    def update_topic_preview(self, *_args):
        topic_id = normalize_id(self.topic_id_var.get())
        title = normalize_title(self.topic_title_var.get())
        if topic_id and title:
            self.topic_preview_var.set(f"→ {self.prefix_var.get()}{topic_id}_{title}")
        else:
            self.topic_preview_var.set("")

    def update_index_preview(self, *_args):
        label = normalize_component(self.index_label_var.get())
        if label:
            self.index_preview_var.set(f"→ {self.prefix_var.get()}Index_{label}")
        else:
            self.index_preview_var.set("")

    def update_other_preview(self, *_args):
        category = normalize_component(self.other_category_var.get(), lowercase=True)
        name = normalize_component(self.other_name_var.get())
        if category and name:
            self.other_preview_var.set(f"→ {self.prefix_var.get()}{category}_{name}")
        else:
            self.other_preview_var.set("")

    def focus_topic_title(self, _event=None):
        self.topic_title_entry.focus_set()
        self.topic_title_entry.icursor(tk.END)
        self.status_var.set("タイトルを入力してEnterで確定します")
        return "break"

    def focus_other_name(self, _event=None):
        category = normalize_component(self.other_category_var.get(), lowercase=True)
        if not category:
            self.status_var.set("分類名を入力してください")
            return "break"
        self.other_category_var.set(category)
        self.other_name_entry.focus_set()
        self.other_name_entry.icursor(tk.END)
        self.status_var.set("日付や題名を入力してEnterで確定します")
        return "break"

    def hide_input(self):
        self.input_frame.pack_forget()
        self.topic_frame.pack_forget()
        self.index_frame.pack_forget()
        self.other_frame.pack_forget()
        self.input_active = False
        self.root.focus_set()

    def cancel_input(self, _event=None):
        self.hide_input()
        self.status_var.set("入力をキャンセルしました")
        return "break"

    def confirm_manual_id(self, _event=None):
        value = normalize_id(self.input_var.get())
        if not value:
            self.status_var.set("IDを入力してください")
            return "break"
        self.commit_id(value)
        return "break"

    def confirm_topic_note(self, _event=None):
        folgezettel_id = normalize_id(self.topic_id_var.get())
        title = normalize_title(self.topic_title_var.get())
        if not folgezettel_id:
            self.status_var.set("番号を入力してください")
            self.topic_id_entry.focus_set()
            return "break"
        if not title:
            self.status_var.set("タイトルを入力してください")
            self.topic_title_entry.focus_set()
            return "break"
        self.commit_topic_note(folgezettel_id, title)
        return "break"

    def confirm_index_note(self, _event=None):
        label = normalize_component(self.index_label_var.get())
        if not label:
            self.status_var.set("Index名を入力してください")
            return "break"
        self.commit_index_note(label)
        return "break"

    def confirm_other_note(self, _event=None):
        category = normalize_component(self.other_category_var.get(), lowercase=True)
        name = normalize_component(self.other_name_var.get())
        if not category:
            self.status_var.set("分類名を入力してください")
            self.other_category_entry.focus_set()
            return "break"
        if not name:
            self.status_var.set("名前を入力してください")
            self.other_name_entry.focus_set()
            return "break"
        self.commit_other_note(category, name)
        return "break"

    def validate_id(self, value: str) -> tuple[bool, str]:
        if not ID_PATTERN.fullmatch(value):
            return False, "IDは数字から始め、数字と英小文字を交互の階層として入力してください（例: 1a2b）。"
        return True, ""

    def validate_title(self, value: str) -> tuple[bool, str]:
        if not value:
            return False, "名称を入力してください"
        if any(ch in INVALID_WINDOWS_CHARS for ch in value):
            return False, '名称には次の文字を使用できません: < > : " / \\ | ? *'
        if value in {".", ".."}:
            return False, "この名称は使用できません"
        return True, ""

    def _commit_current_file(
        self,
        new_name: str,
        *,
        folgezettel_id: Optional[str] = None,
        topic_title: Optional[str] = None,
        note_kind: Optional[str] = None,
        index_label: Optional[str] = None,
        other_category: Optional[str] = None,
        other_name: Optional[str] = None,
    ) -> bool:
        if not self.folder or self.current_index >= len(self.items):
            return False
        item = self.items[self.current_index]
        old_path = item.current_path(self.folder)
        new_path = self.folder / new_name
        if new_path.exists() and new_path.resolve() != old_path.resolve():
            self.status_var.set(f"ファイル「{new_name}」はすでに存在します")
            return False

        old_state = {
            "current_name": item.current_name,
            "folgezettel_id": item.folgezettel_id,
            "topic_title": item.topic_title,
            "processed": item.processed,
            "note_kind": item.note_kind,
            "index_label": item.index_label,
            "other_category": item.other_category,
            "other_name": item.other_name,
        }
        try:
            old_path.rename(new_path)
        except OSError as exc:
            messagebox.showerror("名前を変更できません", f"{old_path.name}\n→ {new_name}\n\n{exc}")
            return False

        item.current_name = new_name
        item.folgezettel_id = folgezettel_id
        item.topic_title = topic_title
        item.note_kind = note_kind
        item.index_label = index_label
        item.other_category = other_category
        item.other_name = other_name
        item.processed = True

        record = {
            "index": self.current_index,
            "old_name": old_state["current_name"],
            "new_name": new_name,
            "old_state": old_state,
            "new_id": folgezettel_id,
            "new_title": topic_title,
        }
        record["markdown_changes"] = self.sync_markdown_after_commit()
        self.undo_stack.append(record)
        self.current_index += 1
        self.hide_input()
        self.save_project()
        self.load_current_image()
        return True

    def commit_id(self, folgezettel_id: str):
        if not self.folder or self.current_index >= len(self.items):
            return
        folgezettel_id = normalize_id(folgezettel_id)
        valid, error = self.validate_id(folgezettel_id)
        if not valid:
            self.status_var.set(error)
            return
        if any(
            item.processed
            and item.folgezettel_id == folgezettel_id
            and not item.topic_title
            for item in self.items
        ):
            self.status_var.set(f"通常ノートのID「{folgezettel_id}」はすでに使用されています")
            return
        old_path = self.items[self.current_index].current_path(self.folder)
        self._commit_current_file(
            f"{self.prefix_var.get()}{folgezettel_id}{old_path.suffix}",
            folgezettel_id=folgezettel_id,
            note_kind="numeric",
        )

    def commit_topic_note(self, folgezettel_id: str, title: str):
        if not self.folder or self.current_index >= len(self.items):
            return
        folgezettel_id = normalize_id(folgezettel_id)
        title = normalize_title(title)
        valid, error = self.validate_id(folgezettel_id)
        if not valid:
            self.status_var.set(error)
            self.topic_id_entry.focus_set()
            return
        valid, error = self.validate_title(title)
        if not valid:
            self.status_var.set(error)
            self.topic_title_entry.focus_set()
            return
        if any(
            other.processed
            and other.folgezettel_id == folgezettel_id
            and normalize_title(other.topic_title or "") == title
            for other in self.items
        ):
            self.status_var.set(f"トピックノート「{folgezettel_id}_{title}」はすでに使用されています")
            return
        old_path = self.items[self.current_index].current_path(self.folder)
        self._commit_current_file(
            f"{self.prefix_var.get()}{folgezettel_id}_{title}{old_path.suffix}",
            folgezettel_id=folgezettel_id,
            topic_title=title,
            note_kind="numeric",
        )

    def commit_index_note(self, label: str):
        if not self.folder or self.current_index >= len(self.items):
            return
        label = normalize_component(label)
        valid, error = self.validate_title(label)
        if not valid:
            self.status_var.set(error)
            return
        if any(
            item.processed
            and item.note_kind == "range_index"
            and normalize_component(item.index_label or "") == label
            for item in self.items
        ):
            self.status_var.set(f"Index「{label}」はすでに使用されています")
            return
        old_path = self.items[self.current_index].current_path(self.folder)
        self._commit_current_file(
            f"{self.prefix_var.get()}Index_{label}{old_path.suffix}",
            note_kind="range_index",
            index_label=label,
        )

    def commit_other_note(self, category: str, name: str):
        if not self.folder or self.current_index >= len(self.items):
            return
        category = normalize_component(category, lowercase=True)
        name = normalize_component(name)
        valid, error = self.validate_title(category)
        if not valid:
            self.status_var.set(error)
            self.other_category_entry.focus_set()
            return
        valid, error = self.validate_title(name)
        if not valid:
            self.status_var.set(error)
            self.other_name_entry.focus_set()
            return
        if category.casefold() == "index":
            self.status_var.set("IndexはIキーで作成してください")
            return
        if ID_PATTERN.fullmatch(category):
            self.status_var.set("数字IDは通常入力またはTキーで作成してください")
            return
        if any(
            item.processed
            and item.note_kind == "other"
            and (item.other_category or "").casefold() == category.casefold()
            and normalize_component(item.other_name or "") == name
            for item in self.items
        ):
            self.status_var.set(f"その他ノート「{category}_{name}」はすでに使用されています")
            return
        old_path = self.items[self.current_index].current_path(self.folder)
        self.other_mode_active = True
        self.other_mode_category = category
        committed = self._commit_current_file(
            f"{self.prefix_var.get()}{category}_{name}{old_path.suffix}",
            note_kind="other",
            other_category=category,
            other_name=name,
        )
        if committed:
            self.save_project()

    def undo_last(self):
        if not self.folder or not self.undo_stack:
            self.status_var.set("戻せる操作がありません")
            return
        record = self.undo_stack.pop()
        index = int(record["index"])
        item = self.items[index]
        current_path = self.folder / record["new_name"]
        restored_path = self.folder / record["old_name"]

        if restored_path.exists() and restored_path.resolve() != current_path.resolve():
            messagebox.showerror("取り消せません", f"元のファイル名「{restored_path.name}」がすでに存在します。")
            self.undo_stack.append(record)
            return
        try:
            current_path.rename(restored_path)
        except OSError as exc:
            messagebox.showerror("取り消せません", str(exc))
            self.undo_stack.append(record)
            return

        restore_markdown_changes(self.folder, record.get("markdown_changes", []))
        old_state = record.get("old_state")
        if old_state:
            item.current_name = old_state.get("current_name", record["old_name"])
            item.folgezettel_id = old_state.get("folgezettel_id")
            item.topic_title = old_state.get("topic_title")
            item.processed = bool(old_state.get("processed", False))
            item.note_kind = old_state.get("note_kind")
            item.index_label = old_state.get("index_label")
            item.other_category = old_state.get("other_category")
            item.other_name = old_state.get("other_name")
        else:
            item.current_name = record["old_name"]
            item.folgezettel_id = record.get("old_id")
            item.topic_title = record.get("old_title")
            item.processed = bool(record.get("old_processed", record.get("old_id")))
            item.note_kind = None
            item.index_label = None
            item.other_category = None
            item.other_name = None
        self.current_index = index
        self.hide_input()
        self.save_project()
        self.load_current_image()
        self.status_var.set("直前の名前変更を取り消しました")

    def finish_work(self):
        self.save_project()
        self.image_canvas.delete("all")
        self.image_canvas.create_text(
            self.image_canvas.winfo_width() // 2,
            self.image_canvas.winfo_height() // 2,
            text="すべての画像の名前付けが完了しました",
            fill="white",
            font=("Yu Gothic UI", 20, "bold"),
            anchor="center",
        )
        self.progress_var.set(f"完了: {len(self.items)} / {len(self.items)}")
        self.current_file_var.set("")
        self.previous_id_var.set(self.previous_id() or "なし")
        self.status_var.set("左矢印で最後の操作を取り消せます")

    def on_close(self):
        self.save_project()
        self.root.destroy()


def _write_error_log(exc_type, exc_value, exc_traceback):
    """起動時・操作時の未処理エラーをファイルへ記録する。"""
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        Path(__file__).with_name("startup_error.log").write_text(details, encoding="utf-8")
    except OSError:
        pass
    try:
        messagebox.showerror(
            "エラーが発生しました",
            "処理を続けられないエラーが発生しました。\n"
            "同じフォルダの startup_error.log を確認してください。",
        )
    except Exception:
        pass


def main():
    sys.excepthook = _write_error_log
    root = tk.Tk()
    root.report_callback_exception = _write_error_log
    try:
        style = ttk.Style(root)
        if sys.platform.startswith("win"):
            style.theme_use("vista")
    except tk.TclError:
        pass
    FolgezettelApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
