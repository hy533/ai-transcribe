import json
import re
from collections.abc import Iterator

import requests

import config

LANG_NAMES = {"zh": "Simplified Chinese (简体中文)", "en": "English", "ja": "Japanese", "ko": "Korean"}

_CJK = re.compile(r"[　-〿぀-ヿ㐀-䶿一-鿿가-힯＀-￯]")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def build_messages(transcript_text: str, language: str, detailed: bool = False) -> list[dict]:
    if language in LANG_NAMES:
        lang_rule = f"Write the summary in {LANG_NAMES[language]}."
    else:
        lang_rule = "Write the summary in the same language as the transcript."
    if detailed:
        system = (
            "You write detailed summaries of video transcripts so a reader knows what the video actually says "
            "without watching it.\n"
            f"{lang_rule}\n"
            "Output markdown in exactly this structure:\n"
            "1. A 1-2 sentence overview of what the video is about.\n"
            "2. The content in the order the video presents it, as 3-8 parts. Each part starts with a bold label "
            "line `**<short part title>**`, followed by a short paragraph or bullet points. For a story, say what "
            "happens, who is involved, and how it turns and ends. For a talk or explainer, give each argument or "
            "step with its evidence.\n"
            "3. A line `**Takeaways**` followed by 3-6 bullet points.\n"
            "The numbers 1-3 above only describe the structure; do not number these parts in your output.\n"
            "Keep concrete details: names, numbers, dates, places, prices, results, and the speaker's actual "
            "conclusions. Use short quotes only when the exact words matter.\n"
            "Do not use markdown headings (no lines starting with #); use only bold labels.\n"
            "Never translate the transcript and never quote it at length; summarize in your own words."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Transcript:\n{transcript_text}"},
        ]
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


def stream_summary(transcript_text: str, language: str, detailed: bool = False) -> Iterator[str]:
    body = {
        "model": config.MODEL,
        "messages": build_messages(transcript_text, language, detailed),
        "stream": True,
        "think": False,
        "keep_alive": "10m",
        "options": {"num_ctx": config.NUM_CTX},
    }
    done = False
    with requests.post(f"{config.OLLAMA_URL}/api/chat", json=body, stream=True, timeout=(5, 300)) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            if "error" in data:
                raise RuntimeError(f"Ollama error: {data['error']}")
            chunk = data.get("message", {}).get("content", "")
            if chunk:
                yield chunk
            if data.get("done"):
                done = True
    if not done:
        raise RuntimeError("Ollama stream ended without a done chunk")
