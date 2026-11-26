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
