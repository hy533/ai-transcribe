import html
import re
from dataclasses import dataclass

from transcript import Segment, normalize_language

_TIME = r"(?:\d+:)?\d+:\d+[.,]\d+"
_TIMING_RE = re.compile(rf"({_TIME})\s*-->\s*{_TIME}")
_TAG_RE = re.compile(r"<[^>]*>")


def _seconds(ts: str) -> float:
    parts = ts.replace(",", ".").split(":")
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    return total


def parse_captions(text: str, ext: str) -> list[Segment]:
    segments: list[Segment] = []
    prev_lines: list[str] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = block.split("\n")
        idx = next((i for i, ln in enumerate(lines) if _TIMING_RE.search(ln)), None)
        if idx is None:
            continue
        start = _seconds(_TIMING_RE.search(lines[idx]).group(1))
        cur = []
        for ln in lines[idx + 1:]:
            ln = html.unescape(_TAG_RE.sub("", ln)).strip()
            if ln:
                cur.append(ln)
        if not cur:
            continue
        overlap = 0
        for k in range(min(len(prev_lines), len(cur)), 0, -1):
            if prev_lines[-k:] == cur[:k]:
                overlap = k
                break
        prev_lines = cur
        fresh = cur[overlap:]
        if fresh:
            segments.append(Segment(start, " ".join(fresh)))
    return segments


@dataclass(frozen=True)
class CaptionTrack:
    lang: str
    kind: str  # "manual"|"auto"
    ext: str
    url: str


def _make_track(lang: str, kind: str, formats: list[dict]) -> CaptionTrack | None:
    for ext in ("vtt", "srt"):
        for f in formats:
            if f.get("ext") == ext and f.get("url"):
                return CaptionTrack(lang, kind, ext, f["url"])
    return None


def _pick_bilibili(subs: dict) -> CaptionTrack | None:
    keys = [k for k in subs if k != "danmaku"]
    for k in [k for k in keys if not k.startswith("ai-")] + [k for k in keys if k.startswith("ai-")]:
        track = _make_track(k, "manual", subs[k])
        if track:
            return track
    return None


def pick_caption_track(info: dict) -> CaptionTrack | None:
    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    if "bili" in (info.get("extractor_key") or "").lower():
        return _pick_bilibili(subs)

    orig = normalize_language(info.get("language"))
    if not orig:
        orig = next((normalize_language(k[: -len("-orig")]) for k in auto if k.endswith("-orig")), "")
    if not orig:
        return None

    candidates = [(k, "manual", subs[k]) for k in subs if normalize_language(k) == orig]
    candidates += [(k, "auto", auto[k]) for k in (f"{orig}-orig", orig) if k in auto]
    for lang, kind, formats in candidates:
        track = _make_track(lang, kind, formats)
        if track:
            return track
    return None
