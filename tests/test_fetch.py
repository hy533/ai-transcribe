import shutil

import pytest

import config
from fetch import PipelineError, build_meta, check_node, source_of, video_key, ydl_opts


def test_ydl_opts_uses_node():
    o = ydl_opts()
    assert o["js_runtimes"] == {"node": {}} and o["noplaylist"] is True and o["extract_flat"] == "in_playlist" and "cookiesfrombrowser" not in o


def test_ydl_opts_cookies(monkeypatch):
    monkeypatch.setattr(config, "COOKIES_BROWSER", "chrome")
    assert ydl_opts()["cookiesfrombrowser"] == ("chrome",)


def test_check_node_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(PipelineError) as e:
        check_node()
    assert e.value.step == "setup"


def test_source_of():
    assert source_of({"extractor_key": "Youtube"}) == "youtube"
    assert source_of({"extractor_key": "BiliBili"}) == "bilibili"


def test_source_of_unsupported():
    with pytest.raises(PipelineError):
        source_of({"extractor_key": "Vimeo"})


@pytest.mark.parametrize("vid,url,expected", [
    ("BV1x", "https://www.bilibili.com/video/BV1x?p=2", "BV1x_p2"),
    ("BV1x_p2", "https://www.bilibili.com/video/BV1x?p=2", "BV1x_p2"),
    ("BV1x", "https://www.bilibili.com/video/BV1x", "BV1x"),
    ("BV1x", "https://www.bilibili.com/video/BV1x?p=1", "BV1x"),
    ("BV1x_p1", "https://www.bilibili.com/video/BV1x?p=1", "BV1x"),
])
def test_video_key_bilibili(vid, url, expected):
    assert video_key({"extractor_key": "BiliBili", "id": vid}, url) == expected


def test_build_meta():
    m = build_meta({"extractor_key": "Youtube", "id": "abc", "title": "T", "uploader": "U", "upload_date": "20261101",
                    "duration": 61, "webpage_url": "https://www.youtube.com/watch?v=abc"}, "https://youtu.be/abc")
    assert (m.video_id, m.channel, m.published, m.duration, m.source, m.url) == (
        "abc", "U", "2026-11-01", 61, "youtube", "https://www.youtube.com/watch?v=abc")


def test_download_audio_no_file_raises(monkeypatch, tmp_path):
    import yt_dlp
    from fetch import download_audio

    class FakeYDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def download(self, urls): pass

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    with pytest.raises(RuntimeError, match="Audio download produced no file"):
        download_audio("u", tmp_path)
