import json
import re
from collections.abc import Iterator

import requests

import config

LANG_NAMES = {"zh": "Simplified Chinese (简体中文)", "en": "English", "ja": "Japanese", "ko": "Korean"}

_CJK = re.compile(r"[　-〿぀-ヿ㐀-䶿一-鿿가-힯＀-￯]")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def build_messages(transcript_text: str, language: str) -> list[dict]:
    if language in LANG_NAMES:
        lang_rule = f"Write the summary in {LANG_NAMES[language]}."
    else:
        lang_rule = "Write the summary in the same language as the transcript."
    system = (
        "You summarize video transcripts so a reader can decide whether the video is worth watching.\n"
        f"{lang_rule}\n"
        "Output markdown in exactly this structure:\n"
        "1. A 2-3 sentence overview of what the video is about.\n"
        "2. A line `**Key points**` followed by 5-8 bullet points.\n"
        "3. A final single line starting with `**Who it's for:**` saying who would benefit from watching.\n"
        "Do not use markdown headings (no lines starting with #); use only the bold labels above.\n"
        "Never translate the transcript and never quote it at length; summarize in your own words."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Transcript:\n{transcript_text}"},
    ]


def estimate_tokens(text: str) -> int:
    cjk = len(_CJK.findall(text))
    return cjk + (len(text) - cjk) // 4


def fits_context(transcript_text: str) -> bool:
    return estimate_tokens(transcript_text) <= config.NUM_CTX - 4096


def strip_think(text: str) -> str:
    return _THINK.sub("", text).strip()


def stream_summary(transcript_text: str, language: str) -> Iterator[str]:
    body = {
        "model": config.MODEL,
        "messages": build_messages(transcript_text, language),
        "stream": True,
        "think": False,
        "keep_alive": "10m",
        "options": {"num_ctx": config.NUM_CTX},
    }
    resp = requests.post(f"{config.OLLAMA_URL}/api/chat", json=body, stream=True, timeout=(5, None))
    resp.raise_for_status()
    for line in resp.iter_lines():
        if not line:
            continue
        chunk = json.loads(line).get("message", {}).get("content", "")
        if chunk:
            yield chunk
