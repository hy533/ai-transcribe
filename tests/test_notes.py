from notes import VideoMeta, find_note, note_filename, parse_note, write_new_note

HOSTILE = 'He said: "Don\'t #panic" — 测试 🎉 [part 1]'


def meta(**kw):
    return VideoMeta(**{"video_id": "abc123", "title": HOSTILE, "channel": "Chan: X", "url": "https://youtu.be/abc123", "source": "youtube", "published": "2026-11-01", "duration": 3753} | kw)


def test_render_parse_roundtrip_hostile_title(tmp_path):
    p = write_new_note(tmp_path, meta(), "zh", "captions", "[00:00] 你好")
    n = parse_note(p)
    assert n.fields["title"] == HOSTILE and n.fields["channel"] == "Chan: X"
    assert n.fields["status"] == "unreviewed" and n.fields["tags"] == ["video"]
    assert n.fields["duration"] == "1:02:33" and n.fields["language"] == "zh"
    assert list(n.fields)[:3] == ["title", "channel", "url"]
    assert n.summary == "" and n.transcript == "[00:00] 你好"


def test_filename_strips_unsafe_chars():
    name = note_filename('a/b:c*d?"e<f>g|h#i^j[k]l', "id1")
    assert name.endswith(" [id1].md") and not set('/:*?"<>|#^[]') & set(name[:-len(" [id1].md")])


def test_filename_truncates_long_title():
    assert len(note_filename("x" * 500, "id1")) <= 130


def test_filename_empty_title_uses_id():
    assert note_filename("???", "id1") == "id1 [id1].md"


def test_find_note_matches_source_and_id(tmp_path):
    p = write_new_note(tmp_path, meta(), "en", "captions", "t")
    write_new_note(tmp_path, meta(source="bilibili", title="other"), "zh", "captions", "t")
    assert find_note(tmp_path, "youtube", "abc123") == p
    assert find_note(tmp_path, "youtube", "nope") is None


def test_find_note_ignores_non_note_md(tmp_path):
    (tmp_path / "random.md").write_text("no frontmatter")
    assert find_note(tmp_path, "youtube", "abc123") is None


def test_filename_long_cjk_title_fits_byte_limit(tmp_path):
    name = note_filename("测" * 200, "id1")
    assert len(name.encode("utf-8")) <= 255 and name.endswith(" [id1].md")
    p = write_new_note(tmp_path, meta(title="测" * 200), "zh", "captions", "t")
    assert p.exists()


def test_filename_strips_leading_dots():
    assert note_filename(".foo", "id1") == "foo [id1].md"
    assert note_filename("...", "id1") == "id1 [id1].md"
