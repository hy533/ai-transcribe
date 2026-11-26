# Apple Podcasts Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apple Podcasts episode links work end to end like YouTube/Bilibili links, and the Whisper step shows length + time estimate.

**Architecture:** Apple Podcasts becomes a third `source` in the existing pipeline (`fetch.source_of` → `"apple_podcasts"`). A pure URL check rejects show links before metadata. The Whisper progress line is built by a pure function in `transcript.py`; the pipeline passes the duration to `on_step`.

**Tech Stack:** Python 3.12, uv, yt-dlp (ApplePodcasts extractor), mlx-whisper, Streamlit, pytest.

**Spec:** `docs/superpowers/specs/2026-11-26-apple-podcasts-design.md`

## Global Constraints

- Source value `apple_podcasts`; display name `Apple Podcasts`.
- Show-link error copy (exact): `That's a show page — open an episode and copy its link.`
- Unknown-site error copy (exact): `Only YouTube, Bilibili and Apple Podcasts links are supported.`
- Link placeholder (exact): `Paste a YouTube, Bilibili or Apple Podcasts link`
- Whisper line (exact, duration known): `Transcribing <format_duration(d)> of audio with Whisper (about <N> min)…`, N = `max(1, round(d / 2100))`. Unknown duration: `Transcribing audio with Whisper…` (current copy).
- Podcast notes: `tags: [podcast]`; all other notes keep `tags: [video]`.
- Watch/Skip labels and status values unchanged. No Library marker.
- Never keep downloaded media (audio stays in a `TemporaryDirectory`).
- Run tests with `uv run pytest`; live tests are `-m live`.

## Review Focus

1. Apple episode link with extra params (`&uo=4`, country code other than `us`) → still accepted; episode id from yt-dlp `id`. Pinned in Task 1 (`test_apple_show_link_detection`).
2. Apple show link (no `i=`) → show-page error, `get_info` never called (no misleading "YouTube changed" hint). Pinned in Task 1.
3. Episode metadata has no `channel`/`uploader` → `channel` = `series`, so header and note aren't blank. Pinned in Task 1.
4. Duration `None` or 0 → Whisper line falls back to the plain copy, no "about 0 min". Pinned in Task 2.
5. Existing YouTube/Bilibili notes and tests unchanged (`tags: [video]`, step lists). Pinned by the existing suite plus Task 1's tag test.

---

### Task 1: Apple Podcasts as a source

**Files:**
- Modify: `fetch.py` (`source_of`, `build_meta`; add `is_apple_show_link`)
- Modify: `notes.py` (`render_note` tags)
- Modify: `pipeline.py` (`ensure_transcript` show-link guard)
- Test: `tests/test_fetch.py`, `tests/test_notes.py`, `tests/test_pipeline.py`

**Interfaces:**
- Produces: `fetch.is_apple_show_link(url: str) -> bool`; `source_of` returns `"apple_podcasts"` for extractor keys containing `applepodcasts` (case-insensitive).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fetch.py
def test_source_of_apple_podcasts():
    assert source_of({"extractor_key": "ApplePodcasts"}) == "apple_podcasts"

def test_source_of_unsupported_message():
    with pytest.raises(PipelineError, match="Only YouTube, Bilibili and Apple Podcasts links are supported."):
        source_of({"extractor_key": "Vimeo"})

def test_build_meta_uses_series_as_channel():
    m = build_meta({"extractor_key": "ApplePodcasts", "id": "1000804177272", "title": "Ep",
                    "series": "The Daily", "duration": 1916, "upload_date": "20261126"},
                   "https://podcasts.apple.com/us/podcast/x/id1200361736?i=1000804177272")
    assert (m.channel, m.source, m.video_id) == ("The Daily", "apple_podcasts", "1000804177272")

def test_apple_show_link_detection():
    assert is_apple_show_link("https://podcasts.apple.com/us/podcast/the-daily/id1200361736")
    assert not is_apple_show_link("https://podcasts.apple.com/us/podcast/x/id1200361736?i=1000804177272&uo=4")
    assert not is_apple_show_link("https://podcasts.apple.com/cn/podcast/x/id1?i=2")
    assert not is_apple_show_link("https://www.youtube.com/watch?v=abc")

# tests/test_notes.py
def test_podcast_note_tag(tmp_path):
    p = write_new_note(tmp_path, meta(source="apple_podcasts"), "en", "whisper", "[00:00] hi")
    assert parse_note(p).fields["tags"] == ["podcast"]

def test_video_note_tag_unchanged(tmp_path):
    p = write_new_note(tmp_path, meta(), "en", "captions", "[00:00] hi")
    assert parse_note(p).fields["tags"] == ["video"]

# tests/test_pipeline.py
def test_apple_show_link_rejected_before_metadata(tmp_path):
    f = Fake(info())
    with pytest.raises(PipelineError, match="That's a show page — open an episode and copy its link."):
        ensure_transcript("https://podcasts.apple.com/us/podcast/the-daily/id1200361736", tmp_path, f.deps(), lambda *a: None)
    # assert the fake's get_info was not called (use the Fake's existing call record, or add one)
```

Use the existing `Fake`/`info` helpers in `tests/test_pipeline.py` and `meta` in `tests/test_notes.py`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest -q tests/test_fetch.py tests/test_notes.py tests/test_pipeline.py`
Expected: the new tests FAIL (ImportError for `is_apple_show_link`, wrong tags, etc.).

- [ ] **Step 3: Implement**
  - `source_of`: add the `applepodcasts` branch; update the unsupported message (exact copy above).
  - `build_meta`: `channel=info.get("channel") or info.get("uploader") or info.get("series") or ""`.
  - `is_apple_show_link`: host `podcasts.apple.com` and no `i` query parameter (`urllib.parse`).
  - `render_note`: `"tags": ["podcast"] if meta.source == "apple_podcasts" else ["video"]`.
  - `ensure_transcript`: first line, before `on_step("metadata")`: raise `PipelineError("metadata", <show-page copy>)` if `is_apple_show_link(url)`.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add fetch.py notes.py pipeline.py tests/
git commit -m "feat: accept Apple Podcasts episode links"
```

### Task 2: Whisper wait line with length + estimate; UI copy

**Files:**
- Modify: `transcript.py` (add `whisper_line`)
- Modify: `pipeline.py` (`_whisper` passes duration to `on_step`)
- Modify: `app.py` (`on_step`, `SOURCE_NAMES`, placeholder)
- Test: `tests/test_transcript.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `transcript.format_duration(seconds) -> str`.
- Produces: `transcript.whisper_line(duration: int | float | None) -> str`. `on_step` is now called as `on_step(step: str, duration: int | None = None)`; only the `"whisper"` step passes a duration. Callers' `on_step` must accept an optional second argument.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_transcript.py
def test_whisper_line_with_duration():
    assert whisper_line(7500) == "Transcribing 2:05:00 of audio with Whisper (about 4 min)…"
    assert whisper_line(600) == "Transcribing 10:00 of audio with Whisper (about 1 min)…"

def test_whisper_line_unknown_duration():
    assert whisper_line(None) == "Transcribing audio with Whisper…"
    assert whisper_line(0) == "Transcribing audio with Whisper…"

# tests/test_pipeline.py
def test_whisper_step_carries_duration(tmp_path):
    calls = []
    f = Fake(info(subtitles={}, duration=1916))   # no captions → Whisper path, model cached
    ensure_transcript("https://www.youtube.com/watch?v=abc", tmp_path, f.deps(),
                      lambda step, duration=None: calls.append((step, duration)))
    assert ("whisper", 1916) in calls
```

Update the existing `run` helper in `tests/test_pipeline.py` so its `on_step` accepts the optional second argument (e.g. `lambda step, *_: steps.append(step)`); existing step-list assertions stay as they are.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest -q tests/test_transcript.py tests/test_pipeline.py`
Expected: new tests FAIL.

- [ ] **Step 3: Implement**
  - `whisper_line`: exact copy and formula from Global Constraints; falsy duration → plain copy.
  - `_whisper(url, deps, on_step, duration)`: call `on_step("whisper", duration)` when cached; `on_step("whisper-download")` unchanged. `ensure_transcript` passes `meta.duration`.
  - `app.py`: `on_step(step, duration=None)` writes `whisper_line(duration)` for `"whisper"`, otherwise `STEP_LINES`; remove the now-unused `"whisper"` entry from `STEP_LINES`. Add `"apple_podcasts": "Apple Podcasts"` to `SOURCE_NAMES`. Placeholder copy from Global Constraints.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add transcript.py pipeline.py app.py tests/
git commit -m "feat: show audio length and time estimate while Whisper runs"
```

### Task 3: Docs and real-episode check

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: Docs.** README: supported links (add Apple Podcasts episode links; show links rejected), note example mentions `tags: [podcast]` and show name in `channel`, maintenance note ("Apple Podcasts episode links only; Spotify is DRM-protected and unsupported"). CLAUDE.md: Known quirks line for Apple Podcasts (no captions → always Whisper; show links rejected), What's built.

- [ ] **Step 2: Real episode.** Run `uv run streamlit run app.py`, paste a public Apple Podcasts episode link (e.g. one from `https://itunes.apple.com/lookup?id=1200361736&entity=podcastEpisode&limit=2`, field `trackViewUrl`). Expected: Whisper line shows length + estimate; note saved with `source: apple_podcasts`, `channel: The Daily`, `tags: [podcast]`, `transcript_source: whisper`; summary in English; no audio file left (`find "$TMPDIR" -name "*.mp3" -mmin -10` empty). Paste the show link → show-page error in red.

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: Apple Podcasts support"
```
