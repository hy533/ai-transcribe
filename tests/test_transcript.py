import pytest

from transcript import (
    Segment,
    format_duration,
    format_timestamp,
    normalize_language,
    plain_text,
    render_transcript,
    whisper_line,
)


@pytest.mark.parametrize("code,expected", [
    ("zh-Hans", "zh"), ("zh-CN", "zh"), ("zh-TW", "zh"), ("ai-zh", "zh"), ("zh", "zh"),
    ("en-US", "en"), ("en-orig", "en"), ("en", "en"), ("ja", "ja"), (None, ""), ("", ""),
])
def test_normalize_language(code, expected):
    assert normalize_language(code) == expected


def test_format_timestamp():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(754.9) == "12:34"
    assert format_timestamp(3753) == "1:02:33"


def test_format_duration():
    assert format_duration(2530) == "42:10"
    assert format_duration(3753) == "1:02:33"
    assert format_duration(None) == ""


def test_render_transcript_merges_short_segments_keeps_text():
    segs = [Segment(0, "Hello"), Segment(2, "world."), Segment(70, "Next part.")]
    out = render_transcript(segs)
    assert out.splitlines()[0].startswith("[00:00] Hello world.")
    assert "Next part." in out
    assert "".join(s.text for s in segs).replace(" ", "") == plain_text(out).replace(" ", "").replace("\n", "")


def test_render_transcript_empty():
    assert render_transcript([]) == ""


def test_render_transcript_cjk_no_space():
    out = render_transcript([Segment(0, "你好"), Segment(1, "世界"), Segment(2, "ok")])
    assert out == "[00:00] 你好世界 ok"


def test_render_transcript_splits_on_span():
    out = render_transcript([Segment(0, "a"), Segment(29, "b"), Segment(30, "c")])
    assert out.splitlines() == ["[00:00] a b", "[00:30] c"]


def test_whisper_line_with_duration():
    assert whisper_line(7500) == "Transcribing 2:05:00 of audio with Whisper (about 4 min)…"
    assert whisper_line(600) == "Transcribing 10:00 of audio with Whisper (about 1 min)…"


def test_whisper_line_unknown_duration():
    assert whisper_line(None) == "Transcribing audio with Whisper…"
    assert whisper_line(0) == "Transcribing audio with Whisper…"


def test_whisper_line_rounds_half_up():
    assert whisper_line(5250) == "Transcribing 1:27:30 of audio with Whisper (about 3 min)…"
