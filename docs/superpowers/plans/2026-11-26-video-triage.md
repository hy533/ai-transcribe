# Video Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Paste a YouTube/Bilibili link → transcript (captions or local Whisper) → streamed Qwen summary → one Obsidian note per video, reviewed in a Streamlit page.

**Architecture:** Pure-logic modules (`captions`, `transcript`, `notes`, `summarize`) are unit-tested offline. `fetch` wraps yt-dlp + mlx-whisper. `pipeline` orchestrates through an injectable `Deps` bundle so every branch is testable with fakes. `app.py` is a thin Streamlit layer. Work is checkpointed to disk: transcript is saved before the summary starts (spec D1).

**Tech Stack:** Python 3.12 (uv), yt-dlp, mlx-whisper, requests, PyYAML, Streamlit, pytest.

**Spec:** `docs/superpowers/specs/2026-11-26-video-triage-design.md`

## Global Constraints
- Vault dir: `/Users/hanyuey/Documents/assetManagement/notes/videos`
- Ollama: `http://localhost:11434`, model `qwen3.8-27b-64k`, `num_ctx` 65536, `"think": false`, `"keep_alive": "10m"`, `"stream": true`. Never pull a model.
- Whisper: `mlx-community/whisper-large-v3-turbo`.
- yt-dlp options always include `js_runtimes: {"node": {}}` and `noplaylist: True`; `cookiesfrombrowser` only when `config.COOKIES_BROWSER` is set (default `None`).
- Transcript text is never altered by the LLM. Audio lives only in a `tempfile.TemporaryDirectory`.
- Frontmatter keys, in order: `title, channel, url, video_id, source, published, duration, processed, language, transcript_source, status, tags`. `status` ∈ `unreviewed|watch|skip`; `tags: [video]`.
- Note filename: `<sanitized title> [<video_id>].md`. Body: `## Summary` then `## Transcript`.
- Timestamps `[mm:ss]`, `[h:mm:ss]` at ≥ 1 hour.
- Chinese summaries in Simplified Chinese.
- Tests: `uv run pytest` is offline; `uv run pytest -m live` hits real Ollama.
- Commits: conventional prefix, end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Work on branch `feature/video-triage`.

## Review Focus
1. **YouTube auto-caption VTT repeats rolling lines** across cues → transcript must not contain each sentence 2–3 times. (Task 2: `test_parse_vtt_dedupes_rolling_lines`)
2. **Caption file parses to zero segments** (empty/garbled) → fall back to Whisper, not an empty note. (Task 7: `test_empty_captions_fall_back_to_whisper`)
3. **Private / members-only / age-restricted / live video** → yt-dlp raises; user sees a "metadata" error, app doesn't crash. (Task 7: `test_metadata_failure_is_pipeline_error`)
4. **Title sanitizes to nothing** (`"???"`, all emoji-stripped punctuation) → filename falls back to the id. (Task 3: `test_filename_empty_title_uses_id`)
5. **User renamed/deleted the `## Summary` heading in Obsidian** → Regenerate re-adds the section above `## Transcript` instead of crashing or duplicating. (Task 4: `test_replace_section_missing_heading_inserts`)

---

### Task 0: Branch and deps

- [ ] `git checkout -b feature/video-triage`
- [ ] `uv add pyyaml`
- [ ] Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = ["live: hits the real local Ollama model"]
addopts = "-m 'not live'"
pythonpath = ["."]
```
- [ ] `uv run pytest` → "no tests ran" (exit 5 is fine). Commit `chore: add pyyaml and pytest config`.

---

### Task 1: Config, language, timestamps

**Files:** Create `config.py`, `transcript.py`; Test `tests/test_transcript.py`

**Interfaces — Produces:**
- `config`: `VAULT_DIR: Path`, `OLLAMA_URL = "http://localhost:11434"`, `MODEL = "qwen3.8-27b-64k"`, `NUM_CTX = 65536`, `WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"`, `COOKIES_BROWSER: str | None = None`, `SIDEBAR_LIMIT = 30`
- `transcript.Segment` — `@dataclass(frozen=True) class Segment: start: float; text: str`
- `transcript.normalize_language(code: str | None) -> str` — base code; `""` for None/unknown
- `transcript.format_timestamp(seconds: float) -> str`
- `transcript.format_duration(seconds: int | None) -> str` — `"42:10"`, `"1:02:33"`, `""` for None
- `transcript.render_transcript(segments: list[Segment]) -> str` — merged lines `"[mm:ss] text"` joined by `\n`
- `transcript.plain_text(transcript_md: str) -> str` — strips `[..]` prefixes (for the LLM)

- [ ] **Step 1: Tests**
```python
@pytest.mark.parametrize("code,expected", [
    ("zh-Hans","zh"),("zh-CN","zh"),("zh-TW","zh"),("ai-zh","zh"),("zh","zh"),
    ("en-US","en"),("en-orig","en"),("en","en"),("ja","ja"),(None,""),("",""),
])
def test_normalize_language(code, expected): assert normalize_language(code) == expected

def test_format_timestamp():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(754.9) == "12:34"
    assert format_timestamp(3753) == "1:02:33"

def test_format_duration():
    assert format_duration(2530) == "42:10"; assert format_duration(3753) == "1:02:33"; assert format_duration(None) == ""

def test_render_transcript_merges_short_segments_keeps_text():
    segs = [Segment(0,"Hello"),Segment(2,"world."),Segment(70,"Next part.")]
    out = render_transcript(segs)
    assert out.splitlines()[0].startswith("[00:00] Hello world.")
    assert "Next part." in out
    assert "".join(s.text for s in segs).replace(" ","") == plain_text(out).replace(" ","").replace("\n","")

def test_render_transcript_empty(): assert render_transcript([]) == ""
```
- [ ] **Step 2:** `uv run pytest tests/test_transcript.py -v` → FAIL (import error).
- [ ] **Step 3: Implement.** `normalize_language`: lowercase, drop a leading `ai-`, take part before first `-`/`_`. Merge rule (`render_transcript`): start a new line when the current line has ≥ 30 s span or ≥ 400 chars; join segment texts with a space, except no space between two CJK characters. Text content unchanged beyond whitespace.
- [ ] **Step 4:** tests PASS.
- [ ] **Step 5:** Commit `feat: config and transcript formatting helpers`.

---

### Task 2: Caption parsing and track selection

**Files:** Create `captions.py`; Test `tests/test_captions.py`, fixtures `tests/fixtures/auto.vtt`, `tests/fixtures/manual.srt`

**Interfaces:**
- Consumes: `Segment`, `normalize_language`
- Produces:
  - `parse_captions(text: str, ext: str) -> list[Segment]` — `ext` ∈ `"vtt"|"srt"`; strips tags (`<c>`, `<00:00:01.000>`), drops empty cues, dedupes rolling repeats
  - `@dataclass(frozen=True) class CaptionTrack: lang: str; kind: str  # "manual"|"auto"; ext: str; url: str`
  - `pick_caption_track(info: dict) -> CaptionTrack | None`

- [ ] **Step 1: Tests**
```python
def test_parse_srt(): # fixture: 2 cues "Hello there." @1.0s, "Second line." @3.5s
    assert parse_captions(read("manual.srt"),"srt") == [Segment(1.0,"Hello there."),Segment(3.5,"Second line.")]

def test_parse_vtt_strips_tags():
    segs = parse_captions(read("auto.vtt"),"vtt"); assert all("<" not in s.text for s in segs)

def test_parse_vtt_dedupes_rolling_lines():   # Review Focus 1
    # auto.vtt: cue1 "we are going", cue2 "we are going\nto the store", cue3 "to the store\ntoday"
    text = " ".join(s.text for s in parse_captions(read("auto.vtt"),"vtt"))
    assert text.count("we are going") == 1 and text.count("to the store") == 1 and "today" in text

def test_parse_garbage_returns_empty(): assert parse_captions("not captions", "vtt") == []

def yt(language=None, subs=None, auto=None):
    return {"extractor_key":"Youtube","language":language,"subtitles":subs or {},"automatic_captions":auto or {}}
def fmt(ext="vtt"): return [{"ext":"json3","url":"j"},{"ext":ext,"url":"u-"+ext}]

def test_manual_original_language_preferred():
    t = pick_caption_track(yt("en", subs={"en":fmt(),"fr":fmt()}, auto={"en-orig":fmt()}))
    assert (t.lang,t.kind,t.ext) == ("en","manual","vtt")

def test_auto_orig_when_no_manual():
    t = pick_caption_track(yt("ja", auto={"ja-orig":fmt(),"en":fmt()}))
    assert (t.lang,t.kind) == ("ja-orig","auto")

def test_translated_auto_rejected():
    assert pick_caption_track(yt("ja", auto={"en":fmt(),"fr":fmt()})) is None

def test_language_inferred_from_orig_track():
    t = pick_caption_track(yt(None, subs={"de":fmt(),"en":fmt()}, auto={"en-orig":fmt()}))
    assert t.lang == "en" and t.kind == "manual"

def test_no_language_info_returns_none():
    assert pick_caption_track(yt(None, subs={"de":fmt(),"en":fmt()})) is None

def test_bilibili_skips_danmaku_prefers_human():
    info = {"extractor_key":"BiliBili","subtitles":{"danmaku":[{"ext":"xml","url":"d"}],"ai-zh":fmt("srt"),"zh-CN":fmt("srt")}}
    t = pick_caption_track(info); assert (t.lang,t.ext) == ("zh-CN","srt")

def test_bilibili_ai_track_used_when_only_one():
    info = {"extractor_key":"BiliBili","subtitles":{"danmaku":[{"ext":"xml","url":"d"}],"ai-zh":fmt("srt")}}
    assert pick_caption_track(info).lang == "ai-zh"

def test_track_without_vtt_or_srt_ignored():
    assert pick_caption_track(yt("en", subs={"en":[{"ext":"json3","url":"j"}]})) is None
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement.** Format preference per track: `vtt`, then `srt`. YouTube original language = `info["language"]`, else the base of the first `*-orig` key in `automatic_captions`, else none → `None`. Order: manual track whose `normalize_language(key) == orig`, then auto key `f"{orig}-orig"`, then auto key exactly `orig`. Bilibili: ignore `danmaku`; prefer keys not starting `ai-`, then `ai-*`. Rolling dedupe: for each cue, drop leading lines equal to the previous cue's trailing lines.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat: caption parsing and track selection`.

---

### Task 3: Note render, parse, find

**Files:** Create `notes.py`; Test `tests/test_notes.py`

**Interfaces:**
- Produces:
  - `@dataclass class VideoMeta: video_id: str; title: str; channel: str; url: str; source: str; published: str; duration: int | None`
  - `@dataclass class Note: path: Path; fields: dict; summary: str; transcript: str`
  - `note_filename(title: str, video_id: str) -> str`
  - `render_note(meta: VideoMeta, language: str, transcript_source: str, transcript_md: str, summary: str = "", processed: str | None = None) -> str` — `processed` defaults to today ISO
  - `write_new_note(vault: Path, meta: VideoMeta, language: str, transcript_source: str, transcript_md: str) -> Path`
  - `parse_note(path: Path) -> Note` — `summary`/`transcript` are section bodies, stripped
  - `find_note(vault: Path, source: str, video_id: str) -> Path | None`

- [ ] **Step 1: Tests**
```python
HOSTILE = 'He said: "Don\'t #panic" — 测试 🎉 [part 1]'
def meta(**kw): return VideoMeta(**{"video_id":"abc123","title":HOSTILE,"channel":"Chan: X","url":"https://youtu.be/abc123","source":"youtube","published":"2026-11-01","duration":3753} | kw)

def test_render_parse_roundtrip_hostile_title(tmp_path):
    p = write_new_note(tmp_path, meta(), "zh", "captions", "[00:00] 你好")
    n = parse_note(p)
    assert n.fields["title"] == HOSTILE and n.fields["channel"] == "Chan: X"
    assert n.fields["status"] == "unreviewed" and n.fields["tags"] == ["video"]
    assert n.fields["duration"] == "1:02:33" and n.fields["language"] == "zh"
    assert list(n.fields)[:3] == ["title","channel","url"]
    assert n.summary == "" and n.transcript == "[00:00] 你好"

def test_filename_strips_unsafe_chars():
    name = note_filename('a/b:c*d?"e<f>g|h#i^j[k]l', "id1")
    assert name.endswith(" [id1].md") and not set('/:*?"<>|#^[]') & set(name[:-len(" [id1].md")])

def test_filename_truncates_long_title(): assert len(note_filename("x"*500,"id1")) <= 130

def test_filename_empty_title_uses_id():   # Review Focus 4
    assert note_filename("???", "id1") == "id1 [id1].md"

def test_find_note_matches_source_and_id(tmp_path):
    p = write_new_note(tmp_path, meta(), "en", "captions", "t")
    write_new_note(tmp_path, meta(source="bilibili", title="other"), "zh", "captions", "t")
    assert find_note(tmp_path, "youtube", "abc123") == p
    assert find_note(tmp_path, "youtube", "nope") is None

def test_find_note_ignores_non_note_md(tmp_path):
    (tmp_path/"random.md").write_text("no frontmatter"); assert find_note(tmp_path,"youtube","abc123") is None
```
- [ ] **Step 2:** FAIL. **Step 3: Implement.** Frontmatter via `yaml.safe_dump(fields, allow_unicode=True, sort_keys=False)` between `---` lines. Sanitize: remove `/\:*?"<>|#^[]` and control chars, collapse whitespace, strip, cap 120 chars; empty → `video_id`. Parse: frontmatter = text between first two `---` lines; sections split on lines starting `## `.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat: note rendering, parsing and lookup`.

---

### Task 4: In-place note edits and library list

**Files:** Modify `notes.py`; Test `tests/test_notes_edit.py`

**Interfaces — Produces:**
- `set_field(path: Path, key: str, value) -> None` — replaces that key's line inside frontmatter only; appends before closing `---` if absent
- `set_status(path: Path, status: str) -> None` — validates `unreviewed|watch|skip` (ValueError otherwise), calls `set_field`
- `replace_section(path: Path, heading: str, body: str) -> None` — `heading` like `"Summary"`
- `@dataclass class NoteInfo: path: Path; title: str; status: str`
- `list_recent(vault: Path, limit: int) -> list[NoteInfo]` — by mtime desc, skips files without our frontmatter

- [ ] **Step 1: Tests** (fixture: a written note, then the user appends a custom field `rating: 5` inside frontmatter, a tag edit `tags: [video, ml]`, and a section `## My notes\nkeep me` at the end)
```python
def test_set_status_only_changes_status_line(user_edited_note):
    before = user_edited_note.read_text(); set_status(user_edited_note, "watch")
    after = user_edited_note.read_text()
    diff = [l for l in after.splitlines() if l not in before.splitlines()]
    assert diff == ["status: watch"]

def test_set_status_rejects_unknown(user_edited_note):
    with pytest.raises(ValueError): set_status(user_edited_note, "maybe")

def test_set_field_does_not_touch_body(user_edited_note):
    replace_section(user_edited_note, "Summary", "status: fake line in body")
    set_status(user_edited_note, "skip")
    assert "status: fake line in body" in user_edited_note.read_text()

def test_set_field_hostile_value(user_edited_note):
    set_field(user_edited_note, "language", 'x: "y"'); assert parse_note(user_edited_note).fields["language"] == 'x: "y"'

def test_replace_summary_keeps_user_section(user_edited_note):
    replace_section(user_edited_note, "Summary", "New summary")
    n = parse_note(user_edited_note); t = user_edited_note.read_text()
    assert n.summary == "New summary" and "## My notes\nkeep me" in t and "rating: 5" in t

def test_replace_section_missing_heading_inserts(user_edited_note):   # Review Focus 5
    p = user_edited_note; p.write_text(p.read_text().replace("## Summary\n", ""))
    replace_section(p, "Summary", "S")
    t = p.read_text(); assert t.count("## Summary") == 1 and t.index("## Summary") < t.index("## Transcript")

def test_list_recent_order_and_limit(tmp_path): ...  # 3 notes with os.utime mtimes; limit=2 → newest two, titles+status correct
def test_list_recent_empty_vault(tmp_path): assert list_recent(tmp_path, 30) == []
```
- [ ] **Step 2:** FAIL. **Step 3: Implement.** `set_field` renders the line with `yaml.safe_dump({key: value}, allow_unicode=True, sort_keys=False).strip()` (multi-line output not expected for scalars). Missing heading: insert `## {heading}\n\n{body}\n\n` before `## Transcript` if present, else append.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat: in-place note edits and library listing`.

---

### Task 5: Summarizer

**Files:** Create `summarize.py`; Test `tests/test_summarize.py`, `tests/test_summarize_live.py`

**Interfaces:**
- Consumes: `config`
- Produces:
  - `LANG_NAMES = {"zh": "Simplified Chinese (简体中文)", "en": "English", "ja": "Japanese", "ko": "Korean"}`
  - `build_messages(transcript_text: str, language: str) -> list[dict]`
  - `estimate_tokens(text: str) -> int` — CJK chars count 1 each, other chars / 4
  - `fits_context(transcript_text: str) -> bool` — `estimate_tokens(...) <= config.NUM_CTX - 4096`
  - `strip_think(text: str) -> str`
  - `stream_summary(transcript_text: str, language: str) -> Iterator[str]` — POSTs `/api/chat` with Global Constraint options, yields `message.content` chunks; lets `requests` exceptions propagate

- [ ] **Step 1: Tests**
```python
def test_prompt_names_language_and_structure():
    sys_msg = build_messages("你好", "zh")[0]["content"]
    assert "Simplified Chinese" in sys_msg and "key points" in sys_msg.lower() and "who" in sys_msg.lower()

def test_prompt_unknown_language_falls_back():
    assert "same language as the transcript" in build_messages("hola", "")[0]["content"]

def test_strip_think():
    assert strip_think("<think>\nhmm\n</think>\n\nAnswer") == "Answer"; assert strip_think("Answer") == "Answer"

def test_estimate_tokens_cjk_vs_latin():
    assert estimate_tokens("你好世界") == 4; assert estimate_tokens("a"*400) == 100

def test_fits_context_boundary():
    assert fits_context("a" * 4 * (65536 - 4096)); assert not fits_context("你" * 65536)

def test_stream_summary_request_and_chunks(monkeypatch):
    # fake requests.post returning iter_lines of 2 JSON lines {"message":{"content":"Hel"}}, {"message":{"content":"lo"},"done":true}
    # assert collected == ["Hel","lo"]; captured json has model qwen3.8-27b-64k, stream True, think False, keep_alive "10m", options.num_ctx 65536
```
Live (`@pytest.mark.live`):
```python
def cjk_ratio(s): return sum('一' <= c <= '鿿' for c in s) / max(len(s), 1)
def test_live_chinese_summary_is_chinese():
    out = strip_think("".join(stream_summary(ZH_SAMPLE, "zh"))); assert cjk_ratio(out) > 0.3
def test_live_english_summary_is_english():
    out = strip_think("".join(stream_summary(EN_SAMPLE, "en"))); assert cjk_ratio(out) < 0.02
```
(`ZH_SAMPLE`/`EN_SAMPLE`: ~150-word hand-written talk excerpts in the test file.)
- [ ] **Step 2:** FAIL. **Step 3: Implement.** System prompt (English) instructs: write in `{LANG_NAMES[lang]}`; output markdown with a 2–3 sentence overview, then `**Key points**` with 5–8 bullets, then `**Who it's for:**` one line; never translate or quote at length. `requests.post(..., stream=True, timeout=(5, None))`.
- [ ] **Step 4:** `uv run pytest tests/test_summarize.py -v` PASS; `uv run pytest -m live -v` PASS (Ollama running). **Step 5:** Commit `feat: ollama summarizer with streaming`.

---

### Task 6: yt-dlp and Whisper adapters

**Files:** Create `fetch.py`; Test `tests/test_fetch.py`

**Interfaces:**
- Consumes: `config`, `VideoMeta`, `CaptionTrack`, `Segment`, `normalize_language`
- Produces:
  - `class PipelineError(Exception): def __init__(self, step: str, message: str)` — `.step`, `.message` (lives here; `pipeline` re-exports)
  - `check_node() -> None` — raises `PipelineError("setup", "Node.js not found. Install with: brew install node")`
  - `ydl_opts() -> dict`
  - `source_of(info: dict) -> str` — `"youtube"|"bilibili"`; else `PipelineError("metadata", "Only YouTube and Bilibili links are supported.")`
  - `video_key(info: dict, url: str) -> str` — Bilibili: ensure `_p{N}` suffix when URL has `p=N`, N > 1
  - `build_meta(info: dict, url: str) -> VideoMeta` — `published` from `upload_date` `YYYYMMDD` → `YYYY-MM-DD` (`""` if missing); `channel` = `channel` or `uploader` or `""`; `url` = `webpage_url` or input
  - Real I/O (not unit-tested; exercised in Task 9): `get_info(url) -> dict`, `fetch_captions(track: CaptionTrack) -> str`, `download_audio(url: str, tmpdir: Path) -> Path`, `whisper_cached() -> bool`, `transcribe(audio: Path) -> tuple[list[Segment], str]`

- [ ] **Step 1: Tests**
```python
def test_ydl_opts_uses_node(): o = ydl_opts(); assert o["js_runtimes"] == {"node": {}} and o["noplaylist"] is True and "cookiesfrombrowser" not in o
def test_ydl_opts_cookies(monkeypatch): monkeypatch.setattr(config,"COOKIES_BROWSER","chrome"); assert ydl_opts()["cookiesfrombrowser"] == ("chrome",)
def test_check_node_missing(monkeypatch):
    monkeypatch.setattr(shutil,"which",lambda _: None)
    with pytest.raises(PipelineError) as e: check_node()
    assert e.value.step == "setup"
def test_source_of(): assert source_of({"extractor_key":"Youtube"})=="youtube"; assert source_of({"extractor_key":"BiliBili"})=="bilibili"
def test_source_of_unsupported():
    with pytest.raises(PipelineError): source_of({"extractor_key":"Vimeo"})
@pytest.mark.parametrize("vid,url,expected",[
  ("BV1x","https://www.bilibili.com/video/BV1x?p=2","BV1x_p2"),
  ("BV1x_p2","https://www.bilibili.com/video/BV1x?p=2","BV1x_p2"),
  ("BV1x","https://www.bilibili.com/video/BV1x","BV1x"),
  ("BV1x","https://www.bilibili.com/video/BV1x?p=1","BV1x"),
])
def test_video_key_bilibili(vid,url,expected): assert video_key({"extractor_key":"BiliBili","id":vid},url)==expected
def test_build_meta():
    m = build_meta({"extractor_key":"Youtube","id":"abc","title":"T","uploader":"U","upload_date":"20261101","duration":61,"webpage_url":"https://www.youtube.com/watch?v=abc"},"https://youtu.be/abc")
    assert (m.video_id,m.channel,m.published,m.duration,m.source,m.url)==("abc","U","2026-11-01",61,"youtube","https://www.youtube.com/watch?v=abc")
```
- [ ] **Step 2:** FAIL. **Step 3: Implement.** `get_info`: `check_node()`, then `YoutubeDL(ydl_opts()).extract_info(url, download=False)`. `fetch_captions`: `ydl.urlopen(track.url).read().decode("utf-8")`. `download_audio`: `format: "bestaudio/best"`, `outtmpl: str(tmpdir/"audio.%(ext)s")`, no postprocessing (mlx-whisper reads via ffmpeg). `whisper_cached`: `huggingface_hub.try_to_load_from_cache(WHISPER_MODEL, "config.json")` is a `str`. `transcribe`: `mlx_whisper.transcribe(str(audio), path_or_hf_repo=WHISPER_MODEL)` → segments from `result["segments"]` (`start`, `text.strip()`), language `normalize_language(result["language"])`.
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat: yt-dlp and whisper adapters`.

---

### Task 7: Pipeline orchestration

**Files:** Create `pipeline.py`; Test `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything above
- Produces:
  - `@dataclass class Deps: get_info; fetch_captions; download_audio; whisper_cached; transcribe; stream_summary` — callables with the Task 5/6 signatures; `Deps.real()` classmethod wires the real ones
  - `ensure_transcript(url: str, vault: Path, deps: Deps, on_step: Callable[[str], None], force: bool = False) -> tuple[Path, bool]` — returns `(note_path, already_existed)`; `on_step` receives `"metadata"`, `"captions"`, `"whisper"`, `"whisper-download"`, `"saved"`
  - `ensure_summary(path: Path, deps: Deps, on_chunk: Callable[[str], None]) -> str`
  - `needs_summary(path: Path) -> bool`

- [ ] **Step 1: Tests** — a `FakeDeps` builder in the test with counters; info dicts reused from Task 2/6 tests.
```python
def test_captions_path_writes_note(tmp_path)           # steps == ["metadata","captions","saved"]; transcript_source "captions"; language "en"; transcribe not called
def test_whisper_path_when_no_track(tmp_path)          # steps include "whisper"; transcript_source "whisper"; language from transcribe ("zh")
def test_whisper_download_step_when_not_cached(tmp_path)  # whisper_cached False → "whisper-download" instead of "whisper"
def test_empty_captions_fall_back_to_whisper(tmp_path) # Review Focus 2: fetch_captions returns "WEBVTT\n\n" → whisper used
def test_audio_tempdir_removed(tmp_path)               # path passed to transcribe no longer exists after return
def test_existing_note_returned_without_work(tmp_path) # second call → (same path, True); fetch/transcribe counters unchanged
def test_metadata_failure_is_pipeline_error(tmp_path)  # Review Focus 3: get_info raises DownloadError("Private video") → PipelineError step "metadata", message mentions the original error and "uv lock --upgrade-package yt-dlp"
def test_unsupported_site(tmp_path)                    # extractor_key Vimeo → PipelineError("metadata")
def test_summary_written_and_streamed(tmp_path)        # chunks ["<think>x</think>","Sum","mary"] → on_chunk got all; note summary == "Summary"; needs_summary False
def test_summary_ollama_down_keeps_note(tmp_path)      # stream raises requests.ConnectionError → PipelineError step "summary", message contains "Ollama isn't running"; note still has transcript, summary ""
def test_summary_too_long(tmp_path)                    # transcript of "你"*70000 → PipelineError("summary", ...too long...); stream not called
def test_needs_summary_true_for_fresh_note(tmp_path)
def test_reprocess_keeps_status_and_user_section(tmp_path)  # set_status watch + append "## My notes"; force=True with new captions → status watch, "## My notes" kept, transcript replaced, summary "", processed updated
```
- [ ] **Step 2:** FAIL. **Step 3: Implement.** Wrap `get_info` exceptions (except `PipelineError`) as `PipelineError("metadata", f"{e}. If YouTube changed, run: uv lock --upgrade-package yt-dlp && uv sync")`. Language: caption track → `normalize_language(track.lang)`, Whisper → its language. On `force` with an existing note: `replace_section` Transcript and Summary(""), `set_field` `language`, `transcript_source`, `processed`. `ensure_summary` sends `plain_text(note.transcript)`. Exceptions from `fetch_captions`/`download_audio`/`transcribe` become `PipelineError("captions"|"whisper", str(e))`. Add an ASCII flow comment at the top of `pipeline.py`:
```
url → get_info → existing note? ─yes→ return (unless force)
                 │no
                 pick_caption_track ─track→ fetch+parse ─empty→┐
                 │none                                         ▼
                 └──────────────→ download_audio → transcribe ─┘→ write note ("saved")
ensure_summary: note → fits_context? → stream → strip_think → replace Summary
```
- [ ] **Step 4:** PASS (full `uv run pytest`). **Step 5:** Commit `feat: checkpointed pipeline orchestration`.

---

### Task 8: Streamlit app

**Files:** Create `app.py`; Modify `CLAUDE.md` (layout, commands, quirks)

**Interfaces — Consumes:** `Deps.real()`, `ensure_transcript`, `ensure_summary`, `needs_summary`, `parse_note`, `set_status`, `list_recent`, `PipelineError`, `config`.

Layout and every state are fixed by the spec's "Design review decisions" section (header bar, 2:3 columns, states table). Implementation choices pinned here:
- [ ] Page config `layout="wide"`, title "Video Triage". On start: `check_node()` and `VAULT_DIR.is_dir()`; failures render `st.error` and `st.stop()`.
- [ ] Current note path in `st.session_state["note"]`. Link input inside `st.form("go", clear_on_submit=False)`.
- [ ] On submit: `st.status` writes one line per `on_step` value (`"whisper-download"` → "First-time Whisper model download (~1.6 GB)…"); `already_existed` → `st.info("Already in your library (processed {processed})")`.
- [ ] After loading any note: if `needs_summary(path)`, call `ensure_summary` streaming into an `st.empty()` placeholder in the summary column (`placeholder.markdown(buffer)`), then `st.rerun()`.
- [ ] Header: `st.markdown(f"### [{title}]({url})")`, caption line `channel · duration · Source · transcript_source`; Watch/Skip `st.button(type="primary" if status==x else "secondary")` → `set_status`, `st.toast`, `st.rerun()`; `st.popover("⋯")` holds "Regenerate summary" (clears Summary via `replace_section(path,"Summary","")`, rerun) and "Reprocess video" (behind `st.dialog` confirm with the spec's copy, then `ensure_transcript(force=True)`).
- [ ] Columns `st.columns([2, 3])`; transcript in `st.container(height=650)`; summary failure → `st.warning("Summary failed — use ⋯ → Regenerate")` plus the error.
- [ ] Sidebar: header "Library", `list_recent(VAULT_DIR, SIDEBAR_LIMIT)`, each as `st.button` labelled `"● "|"✓ "|"– "` + title truncated to 40 chars + "…", `key=str(path)`; empty → `st.caption("No videos yet.")`.
- [ ] `PipelineError` anywhere → `st.error(f"{e.step}: {e.message}")`, link stays in the box.
- [ ] Verify: `uv run streamlit run app.py` starts with no errors; empty-vault page shows "Paste a link to get its transcript and summary." and "No videos yet."
- [ ] CLAUDE.md: update Repo layout, Dev commands (`uv run streamlit run app.py`, `uv run pytest`, `uv run pytest -m live`, `uv lock --upgrade-package yt-dlp && uv sync`), Current State, backlog.
- [ ] Commit `feat: streamlit review UI`.

---

### Task 9: Manual end-to-end check

- [ ] Run the app. Process (1) a captioned English YouTube video, (2) a video with no captions (Whisper path, first run shows download notice), (3) a Chinese Bilibili video.
- [ ] For each: note exists in the vault with correct frontmatter; Obsidian shows properties without errors; summary in the right language; Watch/Skip updates `status:` only; pasting the same link again shows the "Already in your library" banner.
- [ ] Click a sidebar note while a summary streams → reopening the note resumes the summary (D1).
- [ ] Record any quirks (e.g. actual Bilibili caption ext) in CLAUDE.md Known quirks. Commit `docs: e2e findings`.
