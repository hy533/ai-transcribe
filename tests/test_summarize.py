import json

import pytest

import config
from summarize import build_messages, estimate_tokens, fits_context, strip_think, stream_summary


def test_prompt_names_language_and_structure():
    sys_msg = build_messages("你好", "zh")[0]["content"]
    assert "Simplified Chinese" in sys_msg and "key points" in sys_msg.lower() and "Who it's for" in sys_msg
    assert "heading" in sys_msg.lower()


def test_prompt_unknown_language_falls_back():
    assert "same language as the transcript" in build_messages("hola", "")[0]["content"]


def test_transcript_in_user_message_only():
    msgs = build_messages("UNIQUE_TRANSCRIPT", "en")
    assert "UNIQUE_TRANSCRIPT" not in msgs[0]["content"]
    assert msgs[1]["role"] == "user" and "UNIQUE_TRANSCRIPT" in msgs[1]["content"]


def test_strip_think():
    assert strip_think("<think>\nhmm\n</think>\n\nAnswer") == "Answer"
    assert strip_think("Answer") == "Answer"


def test_estimate_tokens_cjk_vs_latin():
    assert estimate_tokens("你好世界") == 4
    assert estimate_tokens("a" * 400) == 100


def test_fits_context_boundary():
    assert fits_context("a" * 4 * (65536 - 4096))
    assert not fits_context("你" * 65536)


def test_stream_summary_request_and_chunks(monkeypatch):
    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            captured["closed"] = True

        def raise_for_status(self):
            captured["checked"] = True

        def iter_lines(self):
            yield json.dumps({"message": {"content": "Hel"}}).encode()
            yield b""
            yield json.dumps({"message": {"content": ""}}).encode()
            yield json.dumps({"message": {"content": "lo"}, "done": True}).encode()

    def fake_post(url, json=None, stream=None, timeout=None):
        captured.update(url=url, json=json, stream=stream, timeout=timeout)
        return FakeResp()

    monkeypatch.setattr("summarize.requests.post", fake_post)
    assert list(stream_summary("text", "en")) == ["Hel", "lo"]
    body = captured["json"]
    assert captured["url"] == config.OLLAMA_URL + "/api/chat"
    assert captured["checked"] and captured["closed"] and captured["stream"] is True
    assert body["model"] == "qwen3.8-27b-64k"
    assert body["stream"] is True and body["think"] is False
    assert body["keep_alive"] == "10m"
    assert body["options"]["num_ctx"] == 65536
    assert body["messages"] == build_messages("text", "en")


def _patch_lines(monkeypatch, lines):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def raise_for_status(self):
            pass

        def iter_lines(self):
            return iter(lines)

    monkeypatch.setattr("summarize.requests.post", lambda *a, **k: FakeResp())


def test_stream_summary_raises_on_midstream_error(monkeypatch):
    _patch_lines(monkeypatch, [
        json.dumps({"message": {"content": "Hi"}}).encode(),
        json.dumps({"error": "runner crashed"}).encode(),
    ])
    gen = stream_summary("t", "en")
    assert next(gen) == "Hi"
    with pytest.raises(RuntimeError, match="Ollama error: runner crashed"):
        next(gen)


def test_stream_summary_raises_if_no_done(monkeypatch):
    _patch_lines(monkeypatch, [json.dumps({"message": {"content": "Hi"}}).encode()])
    with pytest.raises(RuntimeError):
        list(stream_summary("t", "en"))
