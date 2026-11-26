import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from transcript import format_duration

_UNSAFE = re.compile(r'[/\\:*?"<>|#^\[\]\x00-\x1f\x7f]')
MAX_TITLE_CHARS = 120
MAX_FILENAME_BYTES = 255


@dataclass
class VideoMeta:
    video_id: str
    title: str
    channel: str
    url: str
    source: str
    published: str
    duration: int | None


@dataclass
class Note:
    path: Path
    fields: dict
    summary: str
    transcript: str


def note_filename(title: str, video_id: str) -> str:
    clean = re.sub(r"\s+", " ", _UNSAFE.sub("", title)).strip().lstrip(". ")[:MAX_TITLE_CHARS].strip()
    suffix = f" [{video_id}].md"
    while clean and len((clean + suffix).encode("utf-8")) > MAX_FILENAME_BYTES:
        clean = clean[:-1]
    clean = clean.strip()
    return f"{clean or video_id}{suffix}"


def render_note(meta: VideoMeta, language: str, transcript_source: str, transcript_md: str,
                summary: str = "", processed: str | None = None) -> str:
    fields = {
        "title": meta.title,
        "channel": meta.channel,
        "url": meta.url,
        "video_id": meta.video_id,
        "source": meta.source,
        "published": meta.published,
        "duration": format_duration(meta.duration),
        "processed": processed or date.today().isoformat(),
        "language": language,
        "transcript_source": transcript_source,
        "status": "unreviewed",
        "tags": ["podcast"] if meta.source == "apple_podcasts" else ["video"],
    }
    front = yaml.safe_dump(fields, allow_unicode=True, sort_keys=False)
    return f"---\n{front}---\n\n## Summary\n\n{summary}\n\n## Transcript\n\n{transcript_md}\n"


def write_new_note(vault: Path, meta: VideoMeta, language: str, transcript_source: str,
                   transcript_md: str) -> Path:
    path = Path(vault) / note_filename(meta.title, meta.video_id)
    try:
        with open(path, "x", encoding="utf-8") as f:
            f.write(render_note(meta, language, transcript_source, transcript_md))
    except FileExistsError:
        raise ValueError(f"A note named '{path.name}' already exists in the vault") from None
    return path


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """Return (frontmatter_yaml, body) split on the first two lines that are exactly '---'."""
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None


def split_sections(body: str) -> dict[str, str]:
    """Map '## ' heading name to its stripped body."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in body.split("\n"):
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _load_fields(front: str) -> dict | None:
    try:
        fields = yaml.safe_load(front)
    except yaml.YAMLError:
        return None
    return fields if isinstance(fields, dict) else None


def parse_note(path: Path) -> Note:
    parts = split_frontmatter(Path(path).read_text(encoding="utf-8"))
    if parts is None:
        raise ValueError(f"no frontmatter: {path}")
    fields = _load_fields(parts[0])
    if fields is None:
        raise ValueError(f"invalid frontmatter: {path}")
    sections = split_sections(parts[1])
    return Note(Path(path), fields, sections.get("Summary", ""), sections.get("Transcript", ""))


def find_note(vault: Path, source: str, video_id: str) -> Path | None:
    for path in sorted(Path(vault).glob("*.md")):
        try:
            parts = split_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        fields = _load_fields(parts[0]) if parts else None
        if fields and fields.get("source") == source and str(fields.get("video_id")) == video_id:
            return path
    return None


STATUSES = ("unreviewed", "watch", "skip")


def _frontmatter_end(lines: list[str]) -> int | None:
    if not lines or lines[0] != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            return i
    return None


def set_field(path: Path, key: str, value) -> None:
    path = Path(path)
    lines = path.read_text(encoding="utf-8").split("\n")
    end = _frontmatter_end(lines)
    if end is None:
        raise ValueError(f"no frontmatter: {path}")
    new_line = yaml.safe_dump({key: value}, allow_unicode=True, sort_keys=False).strip()
    for i in range(1, end):
        if lines[i].startswith(f"{key}:"):
            lines[i] = new_line
            break
    else:
        lines.insert(end, new_line)
    path.write_text("\n".join(lines), encoding="utf-8")


def set_status(path: Path, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"invalid status: {status}")
    set_field(path, "status", status)


def replace_section(path: Path, heading: str, body: str) -> None:
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    end = _frontmatter_end([l.rstrip("\n") for l in lines])
    first = (end or -1) + 1
    marker = f"## {heading}"
    block = f"{marker}\n\n{body.strip()}\n\n" if body.strip() else f"{marker}\n\n"
    start = next((i for i in range(first, len(lines)) if lines[i].rstrip() == marker), None)
    if start is not None:
        stop = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    else:
        start = stop = next((i for i in range(first, len(lines)) if lines[i].rstrip("\n") == "## Transcript"), len(lines))
        if start == len(lines) and lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if start == len(lines) and lines and lines[-1].strip():
            block = "\n" + block
    lines[start:stop] = [block]
    path.write_text("".join(lines), encoding="utf-8")


@dataclass
class NoteInfo:
    path: Path
    title: str
    status: str


def list_recent(vault: Path, limit: int) -> list[NoteInfo]:
    found = []
    for path in Path(vault).glob("*.md"):
        try:
            parts = split_frontmatter(path.read_text(encoding="utf-8"))
            mtime = path.stat().st_mtime
        except (OSError, UnicodeDecodeError):
            continue
        fields = _load_fields(parts[0]) if parts else None
        if fields and fields.get("video_id") is not None:
            found.append((mtime, NoteInfo(path, str(fields.get("title", path.stem)), str(fields.get("status", "unreviewed")))))
    found.sort(key=lambda x: x[0], reverse=True)
    return [info for _, info in found[:limit]]
