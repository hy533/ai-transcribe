from pathlib import Path

from captions import parse_captions, pick_caption_track
from transcript import Segment


def read(name):
    return (Path(__file__).parent / "fixtures" / name).read_text()


def test_parse_srt():
    assert parse_captions(read("manual.srt"), "srt") == [Segment(1.0, "Hello there."), Segment(3.5, "Second line.")]


def test_parse_vtt_strips_tags():
    segs = parse_captions(read("auto.vtt"), "vtt")
    assert segs and all("<" not in s.text for s in segs)


def test_parse_vtt_dedupes_rolling_lines():
    text = " ".join(s.text for s in parse_captions(read("auto.vtt"), "vtt"))
    assert text.count("we are going") == 1 and text.count("to the store") == 1 and "today" in text


def test_parse_garbage_returns_empty():
    assert parse_captions("not captions", "vtt") == []


def yt(language=None, subs=None, auto=None):
    return {"extractor_key": "Youtube", "language": language, "subtitles": subs or {}, "automatic_captions": auto or {}}


def fmt(ext="vtt"):
    return [{"ext": "json3", "url": "j"}, {"ext": ext, "url": "u-" + ext}]


def test_manual_original_language_preferred():
    t = pick_caption_track(yt("en", subs={"en": fmt(), "fr": fmt()}, auto={"en-orig": fmt()}))
    assert (t.lang, t.kind, t.ext) == ("en", "manual", "vtt")


def test_auto_orig_when_no_manual():
    t = pick_caption_track(yt("ja", auto={"ja-orig": fmt(), "en": fmt()}))
    assert (t.lang, t.kind) == ("ja-orig", "auto")


def test_translated_auto_rejected():
    assert pick_caption_track(yt("ja", auto={"en": fmt(), "fr": fmt()})) is None


def test_language_inferred_from_orig_track():
    t = pick_caption_track(yt(None, subs={"de": fmt(), "en": fmt()}, auto={"en-orig": fmt()}))
    assert t.lang == "en" and t.kind == "manual"


def test_no_language_info_returns_none():
    assert pick_caption_track(yt(None, subs={"de": fmt(), "en": fmt()})) is None


def test_bilibili_skips_danmaku_prefers_human():
    info = {"extractor_key": "BiliBili", "subtitles": {"danmaku": [{"ext": "xml", "url": "d"}], "ai-zh": fmt("srt"), "zh-CN": fmt("srt")}}
    t = pick_caption_track(info)
    assert (t.lang, t.ext) == ("zh-CN", "srt")


def test_bilibili_ai_track_used_when_only_one():
    info = {"extractor_key": "BiliBili", "subtitles": {"danmaku": [{"ext": "xml", "url": "d"}], "ai-zh": fmt("srt")}}
    assert pick_caption_track(info).lang == "ai-zh"


def test_track_without_vtt_or_srt_ignored():
    assert pick_caption_track(yt("en", subs={"en": [{"ext": "json3", "url": "j"}]})) is None
