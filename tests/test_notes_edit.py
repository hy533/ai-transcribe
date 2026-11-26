import os

import pytest

from notes import (VideoMeta, list_recent, parse_note, replace_section, set_field,
                   set_status, write_new_note)


def _meta(vid="abc", title="T"):
    return VideoMeta(vid, title, "Chan", f"https://youtu.be/{vid}", "youtube", "2026-01-01", 61)


@pytest.fixture
def user_edited_note(tmp_path):
    p = write_new_note(tmp_path, _meta(), "en", "captions", "hello")
    t = p.read_text()
    assert "tags:\n- video\n" in t
    t = t.replace("tags:\n- video\n", "tags:\n- video\n- ml\n").replace("status: unreviewed\n", "status: unreviewed\nrating: 5\n")
    p.write_text(t + "\n## My notes\nkeep me\n")
    assert parse_note(p).fields["tags"] == ["video", "ml"]
    return p


def test_set_status_only_changes_status_line(user_edited_note):
    before = user_edited_note.read_text()
    set_status(user_edited_note, "watch")
    after = user_edited_note.read_text()
    diff = [l for l in after.splitlines() if l not in before.splitlines()]
    assert diff == ["status: watch"]


def test_set_status_rejects_unknown(user_edited_note):
    with pytest.raises(ValueError):
        set_status(user_edited_note, "maybe")


def test_set_field_does_not_touch_body(user_edited_note):
    replace_section(user_edited_note, "Summary", "status: fake line in body")
    set_status(user_edited_note, "skip")
    assert "status: fake line in body" in user_edited_note.read_text()
    assert parse_note(user_edited_note).fields["status"] == "skip"


def test_set_field_hostile_value(user_edited_note):
    set_field(user_edited_note, "language", 'x: "y"')
    assert parse_note(user_edited_note).fields["language"] == 'x: "y"'


def test_set_field_appends_when_absent(user_edited_note):
    set_field(user_edited_note, "reviewed", "yes")
    assert parse_note(user_edited_note).fields["reviewed"] == "yes"
    assert "rating: 5" in user_edited_note.read_text()


def test_replace_summary_keeps_user_section(user_edited_note):
    replace_section(user_edited_note, "Summary", "New summary")
    n = parse_note(user_edited_note)
    t = user_edited_note.read_text()
    assert n.summary == "New summary" and "## My notes\nkeep me" in t and "rating: 5" in t
    assert n.transcript == "hello"


def test_replace_section_missing_heading_inserts(user_edited_note):
    p = user_edited_note
    p.write_text(p.read_text().replace("## Summary\n", ""))
    replace_section(p, "Summary", "S")
    t = p.read_text()
    assert t.count("## Summary") == 1 and t.index("## Summary") < t.index("## Transcript")
    assert parse_note(p).summary == "S"


def test_list_recent_order_and_limit(tmp_path):
    paths = []
    for i, (vid, status) in enumerate([("a", "watch"), ("b", "skip"), ("c", "unreviewed")]):
        p = write_new_note(tmp_path, _meta(vid, f"Title {vid}"), "en", "captions", "x")
        set_status(p, status)
        os.utime(p, (1000 + i * 10, 1000 + i * 10))
        paths.append(p)
    (tmp_path / "plain.md").write_text("no frontmatter")
    (tmp_path / "noid.md").write_text("---\ntitle: x\n---\nbody")
    infos = list_recent(tmp_path, 2)
    assert [(i.path, i.title, i.status) for i in infos] == [
        (paths[2], "Title c", "unreviewed"), (paths[1], "Title b", "skip")]


def test_list_recent_empty_vault(tmp_path):
    assert list_recent(tmp_path, 30) == []


def test_replace_section_heading_trailing_space(user_edited_note):
    p = user_edited_note
    p.write_text(p.read_text().replace("## Summary\n", "## Summary \n"))
    replace_section(p, "Summary", "S")
    assert p.read_text().count("## Summary") == 1 and parse_note(p).summary == "S"
