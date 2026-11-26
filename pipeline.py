# url → get_info → existing note? ─yes→ return (unless force)
#                  │no
#                  pick_caption_track ─track→ fetch+parse ─empty→┐
#                  │none                                         ▼
#                  └──────────────→ download_audio → transcribe ─┘→ write note ("saved")
# ensure_summary: note → fits_context? → stream → strip_think → replace Summary
import re
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterator

import requests

import fetch
import summarize
from captions import pick_caption_track, parse_captions
from fetch import PipelineError, build_meta
from notes import find_note, note_filename, parse_note, replace_section, set_field, write_new_note
from transcript import normalize_language, plain_text, render_transcript

__all__ = ["Deps", "PipelineError", "ensure_transcript", "ensure_summary", "needs_summary"]


@dataclass
class Deps:
    get_info: Callable
    fetch_captions: Callable
    download_audio: Callable
    whisper_cached: Callable
    transcribe: Callable
    stream_summary: Callable[[str, str], Iterator[str]]

    @classmethod
    def real(cls) -> "Deps":
        return cls(fetch.get_info, fetch.fetch_captions, fetch.download_audio,
                   fetch.whisper_cached, fetch.transcribe, summarize.stream_summary)


def _whisper(url: str, deps: Deps, on_step: Callable[[str], None]):
    on_step("whisper" if deps.whisper_cached() else "whisper-download")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            audio = deps.download_audio(url, Path(tmp))
            return deps.transcribe(audio)
    except PipelineError:
        raise
    except Exception as e:
        raise PipelineError("whisper", str(e)) from e


def ensure_transcript(url: str, vault: Path, deps: Deps, on_step: Callable[[str], None],
                      force: bool = False) -> tuple[Path, bool]:
    if fetch.is_apple_show_link(url):
        raise PipelineError("metadata", "That's a show page — open an episode and copy its link.")
    on_step("metadata")
    try:
        info = deps.get_info(url)
    except PipelineError:
        raise
    except Exception as e:
        raise PipelineError("metadata", f"{e}. If YouTube changed, run: uv lock --upgrade-package yt-dlp && uv sync") from e
    if info.get("_type") in ("playlist", "multi_video"):
        raise PipelineError("metadata", "Playlists and channels aren't supported — paste a single video link.")
    meta = build_meta(info, url)
    existing = find_note(vault, meta.source, meta.video_id)
    if existing and not force:
        return existing, True

    segments, language, source = [], "", "captions"
    track = pick_caption_track(info)
    if track:
        on_step("captions")
        try:
            segments = parse_captions(deps.fetch_captions(track), track.ext, rolling=(track.kind == "auto"))
        except Exception:
            segments = []
        language = normalize_language(track.lang)
    if not segments:
        segments, language = _whisper(url, deps, on_step)
        source = "whisper"
        if not segments:
            raise PipelineError("whisper", "No speech found in this video.")

    transcript_md = render_transcript(segments)
    if existing:
        replace_section(existing, "Transcript", transcript_md)
        replace_section(existing, "Summary", "")
        set_field(existing, "language", language)
        set_field(existing, "transcript_source", source)
        set_field(existing, "processed", date.today().isoformat())
        path = existing
    else:
        try:
            path = write_new_note(vault, meta, language, source, transcript_md)
        except ValueError as e:
            name = note_filename(meta.title, meta.video_id)
            raise PipelineError("saved", f"A note named '{name}' already exists in the vault but couldn't be matched to this video — rename or fix it, then try again.") from e
    on_step("saved")
    return path, existing is not None


def needs_summary(path: Path) -> bool:
    return not parse_note(path).summary.strip()


def ensure_summary(path: Path, deps: Deps, on_chunk: Callable[[str], None]) -> str:
    note = parse_note(path)
    text = plain_text(note.transcript)
    if not summarize.fits_context(text):
        raise PipelineError("summary", "Transcript is too long for the model's context window (64k tokens). The transcript is saved.")
    chunks = []
    try:
        for chunk in deps.stream_summary(text, str(note.fields.get("language") or "")):
            chunks.append(chunk)
            on_chunk(chunk)
    except requests.ConnectionError as e:
        raise PipelineError("summary", "Ollama isn't running — start it, then Regenerate.") from e
    except Exception as e:
        raise PipelineError("summary", str(e)) from e
    summary = summarize.strip_think("".join(chunks)).strip()
    summary = re.sub(r"^#+[ \t]*(.*?)[ \t]*$", r"**\1**", summary, flags=re.MULTILINE)
    replace_section(path, "Summary", summary)
    return summary
