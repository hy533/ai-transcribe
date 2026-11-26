import re
from dataclasses import dataclass

MAX_SPAN_SECONDS = 30
MAX_LINE_CHARS = 400


@dataclass(frozen=True)
class Segment:
    start: float
    text: str


def normalize_language(code: str | None) -> str:
    if not code:
        return ""
    code = code.lower()
    if code.startswith("ai-"):
        code = code[3:]
    return re.split(r"[-_]", code, maxsplit=1)[0]


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return ""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def whisper_line(duration: int | float | None) -> str:
    if not duration:
        return "Transcribing audio with Whisper…"
    minutes = max(1, round(duration / 2100))
    return f"Transcribing {format_duration(duration)} of audio with Whisper (about {minutes} min)…"


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return 0x4E00 <= o <= 0x9FFF or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF


def render_transcript(segments: list[Segment]) -> str:
    lines: list[str] = []
    line_start = 0.0
    text = ""
    for seg in segments:
        t = seg.text.strip()
        if not t:
            continue
        if text and (seg.start - line_start >= MAX_SPAN_SECONDS or len(text) >= MAX_LINE_CHARS):
            lines.append(f"[{format_timestamp(line_start)}] {text}")
            text = ""
        if not text:
            line_start = seg.start
            text = t
        elif _is_cjk(text[-1]) and _is_cjk(t[0]):
            text += t
        else:
            text += " " + t
    if text:
        lines.append(f"[{format_timestamp(line_start)}] {text}")
    return "\n".join(lines)


def plain_text(transcript_md: str) -> str:
    return "\n".join(re.sub(r"^\[[^\]]*\]\s*", "", ln) for ln in transcript_md.splitlines())
