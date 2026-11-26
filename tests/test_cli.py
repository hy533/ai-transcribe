import json

import requests

import cli
from notes import parse_note
from tests.test_pipeline import Fake, info

URL = "https://www.youtube.com/watch?v=abc"


def run(capsys, argv, fake=None, vault=None):
    code = cli.main(argv, deps=(fake or Fake()).deps(), vault=vault)
    out, err = capsys.readouterr()
    return code, out, err


def test_transcribe_prints_json_with_note_and_summary(capsys, tmp_path):
    code, out, err = run(capsys, ["transcribe", URL], vault=tmp_path)
    assert code == 0
    data = json.loads(out)
    assert data["title"] == "T" and data["source"] == "youtube" and data["language"] == "en"
    assert data["transcript_source"] == "captions" and data["status"] == "unreviewed"
    assert data["existed"] is False and data["summary_error"] is None
    assert parse_note(data["path"]).summary == "Summary"
    assert "metadata" in err  # progress goes to stderr, never stdout


def test_transcribe_existing_note_reports_existed(capsys, tmp_path):
    run(capsys, ["transcribe", URL], vault=tmp_path)
    fake = Fake()
    code, out, _ = run(capsys, ["transcribe", URL], fake=fake, vault=tmp_path)
    assert code == 0 and json.loads(out)["existed"] is True
    assert fake.calls["captions"] == 0 and fake.calls["stream"] == 0


def test_transcribe_no_summary_skips_ollama(capsys, tmp_path):
    fake = Fake()
    code, out, _ = run(capsys, ["transcribe", URL, "--no-summary"], fake=fake, vault=tmp_path)
    assert code == 0 and fake.calls["stream"] == 0
    assert parse_note(json.loads(out)["path"]).summary.strip() == ""


def test_transcribe_summary_failure_keeps_note_exit_0(capsys, tmp_path):
    fake = Fake(stream_exc=requests.ConnectionError())
    code, out, _ = run(capsys, ["transcribe", URL], fake=fake, vault=tmp_path)
    data = json.loads(out)
    assert code == 0 and "Ollama isn't running" in data["summary_error"]


def test_transcribe_pipeline_error_exit_1_json_on_stderr(capsys, tmp_path):
    fake = Fake(info_={"_type": "playlist"} | info())
    code, out, err = run(capsys, ["transcribe", URL], fake=fake, vault=tmp_path)
    assert code == 1 and out == ""
    error = json.loads(err.strip().splitlines()[-1])
    assert error["step"] == "metadata" and "Playlists" in error["error"]


def test_read_list_and_status(capsys, tmp_path):
    _, out, _ = run(capsys, ["transcribe", URL], vault=tmp_path)
    path = json.loads(out)["path"]

    code, out, _ = run(capsys, ["read", path], vault=tmp_path)
    assert code == 0 and out.strip() == "Summary"
    _, out, _ = run(capsys, ["read", path, "--section", "transcript"], vault=tmp_path)
    assert "hello world" in out

    code, out, _ = run(capsys, ["status", path, "watch"], vault=tmp_path)
    assert code == 0 and json.loads(out) == {"path": path, "status": "watch"}

    _, out, _ = run(capsys, ["list"], vault=tmp_path)
    assert json.loads(out) == [{"path": path, "title": "T", "status": "watch"}]
    _, out, _ = run(capsys, ["list", "--status", "skip"], vault=tmp_path)
    assert json.loads(out) == []


def test_read_missing_note_exit_1(capsys, tmp_path):
    code, out, err = run(capsys, ["read", str(tmp_path / "nope.md")], vault=tmp_path)
    assert code == 1 and out == "" and "error" in json.loads(err)
