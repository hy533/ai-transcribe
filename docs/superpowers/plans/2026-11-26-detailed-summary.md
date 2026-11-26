# Detailed Summary on Demand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One click on a note writes a detailed, in-order summary (plot + concrete facts) into a `## Detailed summary` section, kept alongside the short summary.

**Architecture:** `summarize.build_messages`/`stream_summary` gain a `detailed` flag that swaps the system prompt. `pipeline.ensure_detailed_summary` mirrors `ensure_summary` but targets the new section and never runs automatically. The app's summary column becomes two tabs.

**Tech Stack:** Python 3.12, uv, Ollama (`qwen3.8-27b-64k`), Streamlit, PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-11-26-detailed-summary-design.md`

## Global Constraints

- Section heading (exact): `## Detailed summary`, between `## Summary` and `## Transcript`.
- Detailed prompt rules: 1–2 sentence overview; 3–8 parts in the video's order, each starting with a bold label line `**<short part title>**`; keep names, numbers, dates, places, prices, results, conclusions; short quotes only when exact words matter; end with `**Takeaways**` + 3–6 bullets; no `#` headings; same language rule as the short summary; summarize, don't translate or transcribe.
- Short summary is never written by this feature; `needs_summary` ignores the detailed section; nothing auto-generates the detailed summary.
- The detailed section is written only after the stream completes; a failed or interrupted run leaves the note unchanged.
- Errors reuse the short summary's wording (Ollama down, too long).
- Reprocess clears the detailed summary; Regenerate summary doesn't touch it.
- UI copy (exact): tabs `Summary` / `Detailed`; empty-tab line `Follows the video in order and keeps names, numbers and the plot.`; button `Write detailed summary`; ⋯ menu item `Regenerate detailed summary` (only when one exists).

## Review Focus

1. Old notes with no `## Detailed summary` section → parse fine, Detailed tab shows the button. Pinned in Task 1 (`test_parse_note_without_detailed_section`).
2. User added their own sections (e.g. `## My notes`) after Transcript → untouched when the detailed section is written or cleared. Pinned in Task 2.
3. Model returns only whitespace / `<think>` → no empty section written, clear error. Pinned in Task 2.
4. Reprocess of a note that never had a detailed summary → no empty `## Detailed summary` section appears. Pinned in Task 2.
5. Detailed summary output contains `#` headings → demoted to bold so it can't split the note. Pinned in Task 2.

---

### Task 1: Detailed prompt and note field

**Files:**
- Modify: `summarize.py` (`build_messages`, `stream_summary`)
- Modify: `notes.py` (`Note`, `parse_note`)
- Test: `tests/test_summarize.py`, `tests/test_notes.py`

**Interfaces:**
- Produces: `build_messages(transcript_text: str, language: str, detailed: bool = False) -> list[dict]`; `stream_summary(transcript_text: str, language: str, detailed: bool = False) -> Iterator[str]` (passes `detailed` to `build_messages`; request body otherwise unchanged). `Note.detailed: str` (default `""`, last field), from section `Detailed summary`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_summarize.py
def test_detailed_prompt_rules():
    system = build_messages("t", "zh", detailed=True)[0]["content"]
    assert "Simplified Chinese" in system and "**Takeaways**" in system
    assert "order" in system and "names" in system and "numbers" in system
    assert "no lines starting with #" in system

def test_default_prompt_unchanged():
    assert "**Key points**" in build_messages("t", "en")[0]["content"]
    assert "**Takeaways**" not in build_messages("t", "en")[0]["content"]

def test_stream_summary_detailed_uses_detailed_prompt(monkeypatch):
    # reuse the requests.post fake pattern from test_stream_summary_request_and_chunks;
    # assert the posted body's system message contains "**Takeaways**"

# tests/test_notes.py
def test_parse_note_without_detailed_section(tmp_path):
    p = write_new_note(tmp_path, meta(), "en", "captions", "[00:00] hi")
    assert parse_note(p).detailed == ""

def test_parse_note_reads_detailed_section(tmp_path):
    p = write_new_note(tmp_path, meta(), "en", "captions", "[00:00] hi")
    replace_section(p, "Detailed summary", "**Part one**\nstuff")
    assert parse_note(p).detailed == "**Part one**\nstuff"
```

- [ ] **Step 2: Run** `uv run pytest -q tests/test_summarize.py tests/test_notes.py` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** the signatures above; the detailed system prompt states every rule in Global Constraints and keeps the existing `lang_rule` and no-headings sentence verbatim.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat: detailed summary prompt and note section`

### Task 2: `ensure_detailed_summary` and reprocess clearing

**Files:**
- Modify: `pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 1's `stream_summary(..., detailed=True)` via `deps.stream_summary(text, language, detailed=True)`; `Note.detailed`.
- Produces: `ensure_detailed_summary(path: Path, deps: Deps, on_chunk: Callable[[str], None]) -> str`. Raises `PipelineError("summary", ...)` with the same messages as `ensure_summary` for too-long and Ollama-down, and `PipelineError("summary", "The model returned an empty summary — try again.")` for an empty result.

- [ ] **Step 1: Failing tests** (update `Fake.stream` to `stream(text, language, detailed=False)` and record `detailed` in `self.calls`/a list)

```python
def test_detailed_summary_written_between_summary_and_transcript(tmp_path):
    path, _, _ = run(tmp_path, Fake(chunks=("**Part**\n", "body")))
    ensure_summary(path, Fake().deps(), lambda c: None)
    text_before = parse_note(path).summary
    ensure_detailed_summary(path, Fake(chunks=("**Part**\n", "body")).deps(), lambda c: None)
    body = path.read_text()
    assert body.index("## Summary") < body.index("## Detailed summary") < body.index("## Transcript")
    assert parse_note(path).detailed == "**Part**\nbody" and parse_note(path).summary == text_before

def test_detailed_summary_uses_detailed_prompt(tmp_path):
    # Fake records the detailed flag; assert it was True

def test_detailed_keeps_user_sections(tmp_path):
    # append "\n## My notes\nmine\n" to the note; after ensure_detailed_summary the text "## My notes\nmine" is still present

def test_detailed_failure_leaves_note_unchanged(tmp_path):
    # Fake(chunks=("partial",), stream_exc=RuntimeError("boom")); note bytes identical before/after; PipelineError raised

def test_detailed_empty_result_errors(tmp_path):
    # Fake(chunks=("<think>x</think>", "  ")) -> PipelineError match "empty summary"; no "## Detailed summary" in file

def test_detailed_ollama_down(tmp_path):
    # stream_exc=requests.ConnectionError() -> message "Ollama isn't running — start it, then Regenerate."

def test_detailed_headings_demoted(tmp_path):
    # chunks=("# Big\ntext",) -> detailed == "**Big**\ntext"

def test_needs_summary_ignores_detailed(tmp_path):
    # note with summary filled and no detailed -> needs_summary False

def test_reprocess_clears_detailed(tmp_path):
    # write detailed, then run(..., force=True) -> parse_note(path).detailed == ""

def test_reprocess_without_detailed_adds_no_section(tmp_path):
    # run, then run(force=True) -> "## Detailed summary" not in file
```

- [ ] **Step 2: Run** `uv run pytest -q tests/test_pipeline.py` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** `ensure_detailed_summary` sharing the stream → `strip_think` → heading-demotion → `replace_section` path with `ensure_summary` (extract a private helper taking the section name and `detailed` flag); write only non-empty results. In `ensure_transcript`'s reprocess branch, clear `Detailed summary` only if the existing note has that section.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat: ensure_detailed_summary`

### Task 3: Tabs, button, menu item, docs, live check

**Files:**
- Modify: `app.py` (`render_columns`, ⋯ popover, reprocess reset), `README.md`, `CLAUDE.md`
- Test: manual in the browser + `uv run pytest -m live` (add one live test in `tests/test_summarize_live.py`)

**Interfaces:**
- Consumes: `ensure_detailed_summary`, `Note.detailed`.

- [ ] **Step 1: Live test** `test_detailed_summary_live_en_zh`: stream a detailed summary for a short English and a short Chinese transcript; assert `**Takeaways**` present, no line starts with `#`, Chinese output contains CJK. Run `uv run pytest -m live -q` — Expected: pass (Task 1 already provides the prompt).
- [ ] **Step 2: UI.** Summary column: `st.tabs(["Summary", "Detailed"])`; Summary tab keeps today's behaviour. Detailed tab: if an error is stored for this path (separate `st.session_state["detailed_error"]` dict), show it with `st.error`; elif `note.detailed`, `st.markdown` it; else the empty-tab line + `Write detailed summary` button, which streams via a placeholder like the short summary and reruns when done. Popover: `Regenerate detailed summary` (only when `note.detailed`) clears the section + error and triggers the same streaming. `reset_note_state` also pops `detailed_error`.
- [ ] **Step 3: Browser check** with `uv run streamlit run app.py` on an existing note (e.g. the 3Blue1Brown one): tabs show; button writes the detailed summary; it's saved between Summary and Transcript; Regenerate detailed works; short summary unchanged; a Chinese note gets a Chinese detailed summary.
- [ ] **Step 4: Docs.** README usage (Detailed tab, ⋯ item), note format (`## Detailed summary`), CLAUDE.md layout/patterns line.
- [ ] **Step 5: Run** `uv run pytest -q` — Expected: all pass. **Commit** `feat: detailed summary tab and button`
