# Video Triage — Design

## Intent
Personal, local-only tool. The user pastes a YouTube or Bilibili link and quickly decides whether the video is worth watching by reading a summary next to the full transcript. Every processed video becomes a note in their Obsidian vault, so the vault doubles as a searchable library of everything they've triaged. Replaces a paid transcription/summary service with free local tools.

## Goals
- Paste one link (YouTube or Bilibili, incl. short links like `youtu.be`, `b23.tv`) → transcript + summary ready with no further clicks.
- Transcript source: the video's own captions when available; otherwise download audio and transcribe locally with Whisper.
- **The full original transcript is always saved**, verbatim, in the video's original language, with timestamps. The LLM never touches it.
- Summary is written in the **video's language** (Chinese video → Chinese summary; English → English).
- Every processed video is saved automatically as one markdown note in the vault.
- App shows summary and transcript side by side, with Watch / Skip buttons that record the decision on the note.

## Non-goals (MVP)
- Playlists, channels, bulk queues.
- Chatting with / querying the transcript, translation, speaker labels.
- Sites other than YouTube and Bilibili; local files.
- Very long videos beyond the model's context (see Constraints) — no chunked summarisation.
- Hosting, auth, multi-user, Docker.

## Anti-goals (a failure even if it works)
- Transcript altered, cleaned up, or translated by the LLM.
- Pulling/downloading any new Ollama model. Use only the installed `qwen3.8-27b-64k`.
- Sending transcript or video data anywhere except local Ollama.
- Leaving audio files lying around after transcription.

## Constraints
- macOS, Apple M5 Max, 128 GB RAM. Python 3.12 via `uv` (already set up; deps installed: `yt-dlp`, `mlx-whisper`, `streamlit`, `requests`, dev `pytest`).
- `ffmpeg` installed via Homebrew.
- Ollama on `http://localhost:11434`, model `qwen3.8-27b-64k`. Request with `num_ctx` 65536. Qwen3 has a "thinking" mode — disable it (`"think": false`) or strip `<think>…</think>` from output.
- Whisper: `mlx-whisper` with `mlx-community/whisper-large-v3-turbo`; weights download on first use only. Language auto-detected.
- Vault folder: `/Users/hanyuey/Documents/assetManagement/notes/videos` (exists, currently empty).
- Bilibili CC subtitles often require login. Support optional browser cookies (yt-dlp `cookiesfrombrowser`, browser name configurable, default off). If no usable subtitles → Whisper.

## Approaches considered
1. **Streamlit app + separate pipeline module — chosen.** All Python, built-in two-column layout and buttons, least code. Plain look; started with one command.
2. CLI only, review in Obsidian — least code, but no side-by-side view and requires the terminal each time.
3. FastAPI + hand-written HTML — full visual control, roughly double the code plus a frontend to maintain.

User picked 1. The pipeline module is UI-independent, so it can also be called from a script later.

## Design

### Pipeline (per link)
1. **Metadata** — `yt_dlp` `extract_info(download=False)`: id, title, channel/uploader, upload date, duration, webpage URL, extractor (→ `source: youtube|bilibili`), available `subtitles` and `automatic_captions`.
2. **Dedup** — if a note with the same `source` + `video_id` already exists in the vault, load and show it instead of reprocessing (a Reprocess button forces a rerun — see Builder's calls).
3. **Transcript**
   - Captions: prefer manual subtitles in the video's original language, then auto-generated captions in the original language. Never use YouTube's auto-*translated* tracks. Ignore Bilibili danmaku tracks. Parse to segments `(start_seconds, text)`.
   - Otherwise: download audio only (yt-dlp, to a temp dir), run mlx-whisper, take segments, delete the temp dir.
   - Record `transcript_source: captions|whisper` and `language` (caption language code or Whisper-detected language).
4. **Summary** — send transcript text to Ollama with a prompt requiring: output in the same language as the transcript; structure = 2–3 sentence overview, 5–8 key points, one line "who this is for". For Chinese, write in Simplified Chinese (builder's call — see below).
5. **Save note** — write the markdown file (format below). If summarisation fails, still save the note with transcript and an empty summary, and show the error; the user can hit Regenerate.

### Note format
Filename: `<sanitized title> [<video_id>].md` (id keeps names unique; title keeps Obsidian readable).

```markdown
---
title: "..."
channel: "..."
url: https://...
video_id: "..."
source: youtube | bilibili
published: YYYY-MM-DD
duration: "1:02:33"
processed: YYYY-MM-DD
language: en | zh | ...
transcript_source: captions | whisper
status: unreviewed | watch | skip
tags: [video]
---

## Summary
...

## Transcript
[00:00] ...
[00:42] ...
```
Timestamps `[mm:ss]`, or `[h:mm:ss]` past one hour. Segments may be merged into ~paragraph-sized lines so the transcript reads well; text content is not changed.

### UI (Streamlit, single page)
```
[ paste YouTube / Bilibili link ........ ] [ Go ]
✓ metadata  ✓ captions (or: transcribing with Whisper…)  ✓ summary  ✓ saved → <filename>
┌ SUMMARY ─────────────┬ TRANSCRIPT (scrolls) ─────┐
│ overview / points    │ [00:00] ...               │
│ [Watch] [Skip] [Regenerate summary]              │
└──────────────────────┴───────────────────────────┘
Sidebar: recent notes in the vault folder (title + status); clicking one opens it in the same view.
```
- Progress shows each step as it runs; errors name the step that failed.
- Watch / Skip rewrite `status` in the note's frontmatter. Regenerate replaces only the `## Summary` section.
- Video title links to the original URL.

### Code layout (suggested)
```
app.py          # Streamlit UI
pipeline.py     # metadata, captions, whisper, summary orchestration
notes.py        # render / parse / update note files
config.py       # VAULT_DIR, OLLAMA_URL, MODEL, WHISPER_MODEL, COOKIES_BROWSER
tests/          # pytest for pure functions
```
Run: `uv run streamlit run app.py`.

### Testing
TDD on pure logic, no network: caption file parsing (VTT/SRT/json as yt-dlp returns them), caption track selection (original vs translated vs danmaku), timestamp formatting, filename sanitising, note render/parse round-trip, status update, summary-section replacement, `<think>` stripping. Manual end-to-end check with one captioned YouTube video, one uncaptioned video (Whisper path), and one Chinese Bilibili video.

## Left to the builder
- Exact caption format to request from yt-dlp and the parser for it.
- Segment-merging rule for readable transcript lines.
- Prompt wording.
- Streamlit details (session state, how the sidebar list is built, column ratio).

## Builder's calls (flag to user)
- Summary format (overview / 5–8 points / who it's for) — proposed by Claude, user did not object.
- Timestamps in transcript — proposed by Claude.
- Chinese summaries in Simplified Chinese.
- Filename `<title> [<id>].md`; dedup by id.
- Sidebar list of recent notes.
- If a transcript exceeds the 64k context: show a clear error; transcript still saved.
- **Bilibili multi-part videos (分P):** process only the part the link points to (`?p=N`, default 1). One note per part; `video_id` and filename carry a part suffix (`BVxxxx_p2`) so parts don't dedup to each other. Whole-series processing is out of scope (same as playlists).
- **Notes are edited in place.** The user may add their own tags, fields or sections in Obsidian. Status updates change only the `status` line; Regenerate replaces only the text between `## Summary` and the next heading. Unknown frontmatter fields, extra sections and key order are preserved. Round-trip tests cover a note with user additions.
- **Reprocess button** on an existing note: reruns the pipeline (e.g. a bad Whisper run, or captions added later) and replaces only the Summary and Transcript sections. `status`, other frontmatter fields and user sections are kept; pipeline-owned fields (`language`, `transcript_source`, `processed`) are updated.
- **Picking the caption track when YouTube doesn't report the original language:** use the manual track that matches the `-orig` auto-caption language; otherwise fall back to Whisper.

## Engineering review decisions (2026-11-26)
- **D1 Checkpoint to disk.** Streamlit reruns the script on any click, which kills an in-flight run. Write the note as soon as the transcript exists; the summary fills in afterwards. Opening a note whose Summary section is empty triggers summarisation automatically. A click during the summary step costs only that step.
- **D2 yt-dlp uses Node** (`js_runtimes: {"node": {}}`; Homebrew Node v25 is installed). Check at startup that `node` is on PATH and show a clear error if not. CLAUDE.md gets `uv lock --upgrade-package yt-dlp && uv sync` as the "YouTube broke" fix.
- **D3 PyYAML** (declare `pyyaml` in pyproject; it's already installed transitively). New notes are rendered with `yaml.safe_dump(allow_unicode=True, sort_keys=False)`. Edits to existing notes stay line/section-level so user additions survive.
- **D4 `normalize_language()`**: one helper maps caption codes (`zh-Hans`, `zh-CN`, `ai-zh`, `en-US`, …) and Whisper codes to a base code (`zh`, `en`, …). Used by both the note's `language` field and the summary prompt (prompt names the language explicitly).
- **D5 Live language eval**: `pytest -m live` (skipped by default) sends a short Chinese and a short English sample to the real Qwen and asserts the summary language (CJK character ratio).
- **D6 Stream the summary** from Ollama (`stream: true`, `keep_alive: "10m"`) into the UI; write to the note when complete.
- **D7 First-run notice**: if the Whisper model isn't in the Hugging Face cache, show "first-time download (~1.6 GB)" before transcribing.

## Test plan
Unit (default `uv run pytest`, offline, no network/model): caption parsing per format; caption track selection (manual > auto in original language; reject `-translated` and danmaku); `normalize_language` table; Bilibili part id; `strip_think`; timestamp formatting; filename sanitising; note render with hostile titles (quotes, colons, `#`, emoji, Chinese); parse + find by `video_id`; `set_status` and `replace_section` on notes containing user edits; pipeline orchestration with fake fetcher/transcriber/LLM covering: captions path, Whisper path, summary failure keeps note, Ollama down, too-long transcript, existing note opens, empty-summary note resumes, reprocess keeps status and user sections; Node check; unsupported URL error.
Live (`-m live`): D5 language eval.
Manual E2E: one captioned YouTube video, one uncaptioned video (Whisper), one Chinese Bilibili video.

## NOT in scope
- Background worker / job queue (D1 chose checkpointing instead).
- Chunked map-reduce summarisation for transcripts over 64k tokens.
- Playlists, channels, bulk; other sites; translation; diarization.
- Auto-updating yt-dlp (manual command documented instead).

## Failure modes
| Path | Failure | Handled | Tested | User sees |
|---|---|---|---|---|
| metadata | YouTube change breaks yt-dlp | error names step + upgrade hint | unit (fake raises) | clear error |
| captions | only translated/danmaku tracks | fall back to Whisper | unit | normal run |
| whisper | first-run download slow | D7 notice | unit | notice |
| summary | Ollama not running | note saved without summary | unit | error + Regenerate |
| summary | transcript > 64k | error, note saved | unit | clear error |
| UI | click mid-run | D1 checkpoint/resume | unit | summary resumes |

## Design review decisions (2026-11-26)
Supersedes the UI sketch above where they differ. Streamlit default theme; no custom CSS beyond column heights.

### Layout (D2 header bar, D3 2:3 columns)
```
┌ sidebar ──────────┬ main ───────────────────────────────────────────────┐
│ Library (30 most  │ [ Paste a YouTube or Bilibili link        ] [Go]    │  ← st.form, Enter submits
│ recent, newest    ├─────────────────────────────────────────────────────┤
│ first)            │ Title (links to video)                      ⋯ menu  │  ← ⋯ = Regenerate summary,
│ ● unreviewed      │ channel · 42:10 · YouTube · captions                │       Reprocess video
│ ✓ watch           │ [ Watch ] [ Skip ]   status: unreviewed             │
│ – skip            ├──────────────────┬──────────────────────────────────┤
│ (title, 1 line,   │ SUMMARY  (2)     │ TRANSCRIPT  (3)                  │
│  truncated …)     │ overview         │ [00:00] …                        │
│                   │ • key points     │ [00:42] …   (own scroll,         │
│                   │ For: …           │             fixed height)        │
└───────────────────┴──────────────────┴──────────────────────────────────┘
```
Hierarchy: 1) link box, 2) title + Watch/Skip, 3) summary, 4) transcript, 5) library. The active status button is shown as primary (filled). Long titles wrap in the header and truncate with … in the sidebar.

### States
| Feature | Loading | Empty | Error | Success | Partial |
|---|---|---|---|---|---|
| Main area | `st.status` with checklist: metadata → captions/Whisper (with D7 first-download note) → saved → summary | First launch / nothing selected: one line "Paste a link to get its transcript and summary." | Red `st.error` naming the step + plain fix (e.g. "Ollama isn't running — start it, then Regenerate"). Link stays in the box for retry. | Status collapses to "Saved → <filename>" | Transcript shown, summary column says "Summary failed — Regenerate" |
| Summary | Streams text live (D6) | — | see Partial | rendered markdown | auto-resumes when note opened with empty summary (D1) |
| Already-seen link | — | — | — | Info banner: "Already in your library (processed <date>)" + note loads instantly | — |
| Library sidebar | — | "No videos yet." | Vault folder missing → error with the path | list | — |
| Watch/Skip | — | — | write fails → toast error | `st.toast("Marked as watch")` | — |
| Reprocess | confirm dialog first ("Replaces transcript and summary; keeps your status and notes") | — | as Main | as Main | — |

### NOT in scope (design)
- Custom theme/fonts, mobile layout (localhost on the Mac only), sidebar search/filter (Obsidian search covers it), transcript click-to-seek.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 7 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAR | score: 5/10 → 9/10, 3 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **UNRESOLVED:** 0
- **VERDICT:** ENG + DESIGN CLEARED — ready for implementation plan.
