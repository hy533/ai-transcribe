from datetime import date
from pathlib import Path

import pytest
import requests
from yt_dlp.utils import DownloadError

from notes import parse_note, set_field, set_status
from pipeline import Deps, PipelineError, ensure_summary, ensure_transcript, needs_summary
from transcript import Segment

VTT = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello world\n"


def info(**kw):
    return {"extractor_key": "Youtube", "id": "abc", "title": "T", "uploader": "U",
            "upload_date": "20261101", "duration": 61,
            "webpage_url": "https://www.youtube.com/watch?v=abc", "language": "en",
            "subtitles": {"en": [{"ext": "vtt", "url": "u"}]}, "automatic_captions": {}} | kw


class Fake:
    def __init__(self, info_=None, captions=VTT, cached=True, chunks=("Sum", "mary"), stream_exc=None,
                 audio_exc=None, transcribe_exc=None, whisper_result=([Segment(0.0, "你好")], "zh")):
        self.audio_exc, self.transcribe_exc, self.whisper_result = audio_exc, transcribe_exc, whisper_result
        self.info = info_ or info()
        self.captions = captions
        self.cached = cached
        self.chunks = chunks
        self.stream_exc = stream_exc
        self.calls = {"captions": 0, "audio": 0, "transcribe": 0, "stream": 0}
        self.audio_paths = []

    def deps(self):
        def get_info(url):
            if isinstance(self.info, Exception):
                raise self.info
            return self.info

        def fetch_captions(track):
            self.calls["captions"] += 1
            if isinstance(self.captions, Exception):
                raise self.captions
            return self.captions

        def download_audio(url, tmpdir):
            self.calls["audio"] += 1
            if self.audio_exc:
                raise self.audio_exc
            p = Path(tmpdir) / "a.m4a"
            p.write_bytes(b"x")
            self.audio_paths.append(p)
            return p

        def transcribe(audio):
            self.calls["transcribe"] += 1
            if self.transcribe_exc:
                raise self.transcribe_exc
            return self.whisper_result

        def stream(text, language):
            self.calls["stream"] += 1
            yield from self.chunks
            if self.stream_exc:
                raise self.stream_exc

        return Deps(get_info, fetch_captions, download_audio, lambda: self.cached, transcribe, stream)


def run(tmp_path, fake, force=False):
    steps = []
    path, existed = ensure_transcript("https://www.youtube.com/watch?v=abc", tmp_path, fake.deps(), steps.append, force)
    return path, existed, steps


def test_captions_path_writes_note(tmp_path):
    f = Fake()
    path, existed, steps = run(tmp_path, f)
    n = parse_note(path)
    assert steps == ["metadata", "captions", "saved"] and not existed
    assert n.fields["transcript_source"] == "captions" and n.fields["language"] == "en"
    assert f.calls["transcribe"] == 0 and "hello world" in n.transcript


def test_whisper_path_when_no_track(tmp_path):
    f = Fake(info(subtitles={}))
    path, _, steps = run(tmp_path, f)
    n = parse_note(path)
    assert "whisper" in steps and steps[-1] == "saved"
    assert n.fields["transcript_source"] == "whisper" and n.fields["language"] == "zh"


def test_whisper_download_step_when_not_cached(tmp_path):
    _, _, steps = run(tmp_path, Fake(info(subtitles={}), cached=False))
    assert "whisper-download" in steps and "whisper" not in steps


def test_empty_captions_fall_back_to_whisper(tmp_path):
    f = Fake(captions="WEBVTT\n\n")
    path, _, steps = run(tmp_path, f)
    assert f.calls["transcribe"] == 1 and "whisper" in steps
    assert parse_note(path).fields["transcript_source"] == "whisper"


def test_audio_tempdir_removed(tmp_path):
    f = Fake(info(subtitles={}))
    run(tmp_path, f)
    assert f.audio_paths and not f.audio_paths[0].exists() and not f.audio_paths[0].parent.exists()


def test_existing_note_returned_without_work(tmp_path):
    f = Fake()
    p1, _, _ = run(tmp_path, f)
    before = dict(f.calls)
    p2, existed, _ = run(tmp_path, f)
    assert p2 == p1 and existed and f.calls == before


def test_metadata_failure_is_pipeline_error(tmp_path):
    with pytest.raises(PipelineError) as e:
        run(tmp_path, Fake(DownloadError("Private video")))
    assert e.value.step == "metadata"
    assert "Private video" in e.value.message and "uv lock --upgrade-package yt-dlp" in e.value.message


def test_unsupported_site(tmp_path):
    with pytest.raises(PipelineError) as e:
        run(tmp_path, Fake(info(extractor_key="Vimeo")))
    assert e.value.step == "metadata" and "YouTube, Bilibili and Apple Podcasts" in e.value.message


def test_summary_written_and_streamed(tmp_path):
    f = Fake(chunks=["<think>x</think>", "Sum", "mary"])
    path, _, _ = run(tmp_path, f)
    got = []
    out = ensure_summary(path, f.deps(), got.append)
    assert got == ["<think>x</think>", "Sum", "mary"] and out == "Summary"
    assert parse_note(path).summary == "Summary" and not needs_summary(path)


def test_summary_ollama_down_keeps_note(tmp_path):
    f = Fake(stream_exc=requests.ConnectionError("refused"), chunks=())
    path, _, _ = run(tmp_path, f)
    with pytest.raises(PipelineError) as e:
        ensure_summary(path, f.deps(), lambda c: None)
    assert e.value.step == "summary" and "Ollama isn't running" in e.value.message
    n = parse_note(path)
    assert "hello world" in n.transcript and n.summary == ""


def test_summary_other_error_uses_message(tmp_path):
    f = Fake(stream_exc=RuntimeError("model not found"), chunks=())
    path, _, _ = run(tmp_path, f)
    with pytest.raises(PipelineError) as e:
        ensure_summary(path, f.deps(), lambda c: None)
    assert e.value.step == "summary" and e.value.message == "model not found"


def test_summary_too_long(tmp_path):
    f = Fake(captions="WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n" + "你" * 70000 + "\n")
    path, _, _ = run(tmp_path, f)
    with pytest.raises(PipelineError) as e:
        ensure_summary(path, f.deps(), lambda c: None)
    assert e.value.step == "summary" and "too long" in e.value.message and f.calls["stream"] == 0


def test_needs_summary_true_for_fresh_note(tmp_path):
    path, _, _ = run(tmp_path, Fake())
    assert needs_summary(path)


def test_reprocess_keeps_status_and_user_section(tmp_path):
    f = Fake()
    path, _, _ = run(tmp_path, f)
    ensure_summary(path, f.deps(), lambda c: None)
    set_status(path, "watch")
    set_field(path, "processed", "2020-01-01")
    path.write_text(path.read_text().rstrip("\n") + "\n\n## My notes\n\nkeep me\n")
    f.captions = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nbrand new text\n"
    p2, existed, _ = run(tmp_path, f, force=True)
    n = parse_note(p2)
    assert p2 == path and existed
    assert n.fields["status"] == "watch" and "keep me" in path.read_text()
    assert "brand new text" in n.transcript and "hello world" not in n.transcript
    assert n.summary == "" and n.fields["processed"] == date.today().isoformat()


class HTTP429(Exception):
    pass


def test_caption_fetch_error_falls_back_to_whisper(tmp_path):
    f = Fake(captions=HTTP429("HTTP Error 429"))
    path, _, steps = run(tmp_path, f)
    assert f.calls["transcribe"] == 1 and "whisper" in steps
    assert parse_note(path).fields["transcript_source"] == "whisper"


def test_whisper_download_failure_is_pipeline_error(tmp_path):
    with pytest.raises(PipelineError) as e:
        run(tmp_path, Fake(info(subtitles={}), audio_exc=RuntimeError("no audio")))
    assert e.value.step == "whisper" and "no audio" in e.value.message


def test_whisper_transcribe_failure_is_pipeline_error(tmp_path):
    with pytest.raises(PipelineError) as e:
        run(tmp_path, Fake(info(subtitles={}), transcribe_exc=RuntimeError("boom")))
    assert e.value.step == "whisper" and e.value.message == "boom"


def test_empty_captions_language_becomes_whisper_language(tmp_path):
    path, _, _ = run(tmp_path, Fake(captions="WEBVTT\n\n"))
    assert parse_note(path).fields["language"] == "zh"


def test_whisper_no_segments_is_error(tmp_path):
    with pytest.raises(PipelineError) as e:
        run(tmp_path, Fake(info(subtitles={}), whisper_result=([], "en")))
    assert e.value.step == "whisper" and e.value.message == "No speech found in this video."


def test_playlist_rejected(tmp_path):
    for t in ("playlist", "multi_video"):
        with pytest.raises(PipelineError) as e:
            run(tmp_path, Fake(info(_type=t)))
        assert e.value.step == "metadata" and "Playlists and channels" in e.value.message


def test_existing_unmatched_file_not_overwritten(tmp_path):
    from notes import note_filename
    clash = tmp_path / note_filename("T", "abc")
    clash.write_text("hand edited, no frontmatter")
    with pytest.raises(PipelineError) as e:
        run(tmp_path, Fake())
    assert e.value.step == "saved" and "already exists" in e.value.message and note_filename("T", "abc") in e.value.message
    assert clash.read_text() == "hand edited, no frontmatter"


def test_summary_headings_demoted(tmp_path):
    f = Fake(chunks=["## Foo\nbody\n", "# Bar\n**Who it's for:** x"])
    path, _, _ = run(tmp_path, f)
    out = ensure_summary(path, f.deps(), lambda c: None)
    assert "## " not in out and "**Foo**" in out and "**Bar**" in out
    assert set(__import__("notes").split_sections(path.read_text().split("---\n", 2)[2])) == {"Summary", "Transcript"}


def test_apple_show_link_rejected_before_metadata(tmp_path):
    f = Fake(RuntimeError("get_info must not be called"))
    with pytest.raises(PipelineError, match="That's a show page — open an episode and copy its link."):
        ensure_transcript("https://podcasts.apple.com/us/podcast/the-daily/id1200361736", tmp_path, f.deps(), lambda *a: None)
