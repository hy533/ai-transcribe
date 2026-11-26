import re
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import config
from captions import CaptionTrack
from notes import VideoMeta
from transcript import Segment, normalize_language


class PipelineError(Exception):
    def __init__(self, step: str, message: str):
        super().__init__(message)
        self.step = step
        self.message = message


def check_node() -> None:
    if shutil.which("node") is None:
        raise PipelineError("setup", "Node.js not found. Install with: brew install node")


def ydl_opts() -> dict:
    opts = {
        "js_runtimes": {"node": {}},
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
    }
    if config.COOKIES_BROWSER:
        opts["cookiesfrombrowser"] = (config.COOKIES_BROWSER,)
    return opts


def source_of(info: dict) -> str:
    key = (info.get("extractor_key") or "").lower()
    if "youtube" in key:
        return "youtube"
    if "bili" in key:
        return "bilibili"
    if "applepodcasts" in key:
        return "apple_podcasts"
    raise PipelineError("metadata", "Only YouTube, Bilibili and Apple Podcasts links are supported.")


APPLE_HOSTS = ("podcasts.apple.com", "itunes.apple.com")


def is_apple_show_link(url: str) -> bool:
    parsed = urlparse(url)
    episode = parse_qs(parsed.query).get("i", [""])[0]
    return parsed.hostname in APPLE_HOSTS and not episode.isdigit()


def normalize_link(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname == "itunes.apple.com":
        return parsed._replace(netloc="podcasts.apple.com").geturl()
    return url


def video_key(info: dict, url: str) -> str:
    vid = info["id"]
    if source_of(info) == "bilibili":
        p = parse_qs(urlparse(url).query).get("p", [""])[0]
        if p.isdigit() and int(p) > 1 and not re.search(rf"_p{int(p)}$", vid):
            return f"{vid}_p{int(p)}"
        return re.sub(r"_p1$", "", vid)
    return vid


def build_meta(info: dict, url: str) -> VideoMeta:
    d = info.get("upload_date") or ""
    published = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else ""
    return VideoMeta(
        video_id=video_key(info, url),
        title=info.get("title") or "",
        channel=info.get("channel") or info.get("uploader") or info.get("series") or "",
        url=info.get("webpage_url") or url,
        source=source_of(info),
        published=published,
        duration=info.get("duration"),
    )


def get_info(url: str) -> dict:
    from yt_dlp import YoutubeDL
    check_node()
    with YoutubeDL(ydl_opts()) as ydl:
        return ydl.extract_info(url, download=False)


def fetch_captions(track: CaptionTrack) -> str:
    if track.data is not None:
        return track.data
    from yt_dlp import YoutubeDL
    with YoutubeDL(ydl_opts()) as ydl:
        return ydl.urlopen(track.url).read().decode("utf-8")


def download_audio(url: str, tmpdir: Path) -> Path:
    from yt_dlp import YoutubeDL
    opts = {**ydl_opts(), "format": "bestaudio/best", "http_chunk_size": 10 * 1024 * 1024, "noprogress": True, "outtmpl": str(tmpdir / "audio.%(ext)s")}
    with YoutubeDL(opts) as ydl:
        ydl.download([url])
    try:
        return next(tmpdir.glob("audio.*"))
    except StopIteration:
        raise RuntimeError("Audio download produced no file") from None


def whisper_cached() -> bool:
    from huggingface_hub import try_to_load_from_cache
    return isinstance(try_to_load_from_cache(config.WHISPER_MODEL, "config.json"), str)


def transcribe(audio: Path) -> tuple[list[Segment], str]:
    import mlx_whisper
    result = mlx_whisper.transcribe(str(audio), path_or_hf_repo=config.WHISPER_MODEL)
    segments = [Segment(s["start"], s["text"].strip()) for s in result["segments"]]
    return segments, normalize_language(result["language"])
