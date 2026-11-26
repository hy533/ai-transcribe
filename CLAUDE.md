## Last Resumed: 2026-11-26 17:13
All pipeline modules and the Streamlit UI are built and reviewed on `feature/video-triage` (93 offline + 2 live tests passing). In progress: Task 9, the real-link end-to-end check on three user-supplied links (two YouTube, one Bilibili). Next: record findings, commit `docs: e2e findings`, then finish the branch (merge/PR only with the user's OK).

## Current State (2026-11-26)
Pipeline modules and the Streamlit UI (`app.py`) are built on branch `feature/video-triage`. app.py has no unit tests (verified via Streamlit AppTest only); real-link end-to-end check (Task 9) passed 2026-11-26.

# AI Transcribe

## What this is
A personal, local-only tool for deciding whether a YouTube or Bilibili video is worth watching, and keeping what's learned in Obsidian. Paste a link → get the full transcript (existing captions if available, otherwise local Whisper) → generate a summary with a local Ollama model → save everything as one markdown note in the Obsidian vault. The vault *is* the library; there is no separate database.

## Workflow
Follows the global workflow. Single user, runs only on this Mac.

## Stack
| Piece | Choice |
|---|---|
| Language / env | Python 3.12 via `uv` (project-local `.venv`) |
| Download captions + audio | `yt-dlp` (YouTube + Bilibili) |
| Transcription fallback | `mlx-whisper` (Apple GPU; weights download on first use only) |
| Summary | Ollama at `localhost:11434`, model `qwen3.8-27b-64k` (already installed — do not pull other models) |
| UI | Streamlit, single page on localhost |
| Output | Markdown notes in `/Users/hanyuey/Documents/assetManagement/notes/videos` |

## Repo layout
```
app.py           # Streamlit UI only (sidebar, header, summary/transcript columns)
pipeline.py      # ensure_transcript / ensure_summary orchestration (Deps injected for tests)
fetch.py         # yt-dlp metadata/captions/audio, Whisper, PipelineError, check_node
captions.py      # pick caption track, parse VTT/JSON captions
transcript.py    # segments -> markdown transcript, language normalizing
summarize.py     # Ollama streaming summary, context-fit check, <think> stripping
notes.py         # note format: write/parse/find, set_status, replace_section, list_recent
cli.py           # command-line front end for agents/scripts (transcribe/read/list/status, JSON on stdout)
config.py        # vault path, model, limits
tests/           # pytest (live tests marked `live`)
docs/superpowers/ # specs and plans
pyproject.toml   # deps (managed by uv)
uv.lock          # locked versions
CLAUDE.md        # this file
```

## Dev commands
```bash
uv sync                                          # install/refresh deps
uv run streamlit run app.py                      # run the app (localhost)
uv run pytest                                    # tests
uv run pytest -m live                            # live tests (network/Ollama)
uv lock --upgrade-package yt-dlp && uv sync      # fix "site changed" metadata errors
uv add <pkg>                                     # add a dependency
```

## Data model
One note per video (format TBD in spec): frontmatter (title, channel, url, source, date) + summary + transcript.

## Key patterns
- app.py is a thin UI layer; all logic lives in pipeline/notes. Current note path is `st.session_state["note"]`; summary failures are kept in `st.session_state["summary_error"]` to avoid retry loops until Regenerate.
- cli.py is a thin front end like app.py: stdout is only the result (JSON / plain text), progress + errors go to stderr; exit 1 on failure. MCP server and HTTP service are deliberately not built yet (CLI first; add only when Muse/n8n need them).
- Status is stored in the note frontmatter (`unreviewed` / `watch` / `skip`).
- Never keep downloaded media: audio goes to a `TemporaryDirectory` and is deleted right after transcription (before the Watch/Skip decision). Only the markdown note persists.

## Known quirks
- No Docker: containers on macOS can't use Metal, so mlx-whisper would fall back to CPU.
- Bilibili CC subtitles often require login cookies; fall back to Whisper if unavailable.
- Bilibili subtitles arrive from yt-dlp as inline `data` (SRT text, no `url`); `CaptionTrack.data` carries it and `fetch_captions` returns it directly.
- `yt-dlp-ejs` is required for YouTube JS challenges (node solver script); it is a project dependency.
- Playlists, channels and multi-video links are rejected (single video only).
- Apple Podcasts: episode links only (`?i=` required; show links rejected before yt-dlp runs). No captions, so always Whisper. Show name comes from yt-dlp `series` → `channel`; notes get `tags: [podcast]`.
- Rolling-line dedupe applies only to auto captions; manual captions stay verbatim.
- Ollama's default context is short; use the `-64k` model variant for long transcripts.
- Bilibili's CDN answers a single whole-file audio request with HTTP 567/403; `download_audio` sets `http_chunk_size` (10 MB ranges), which works.
- Whisper sometimes writes Chinese in Traditional characters (seen on a Bilibili video); the summary is still Simplified.
- The summary labels "Key points" / "Who it's for" stay English in Chinese summaries, and Qwen occasionally drops the "Who it's for" line.

## What's built / backlog
- [x] Apple Podcasts episode links (branch `feature/apple-podcasts`, 2026-11-26)
- [x] Environment
- [x] Pipeline modules + Streamlit UI
- [x] End-to-end check with real links (Task 9, 2026-11-26): YouTube captions, YouTube Whisper (zh), Bilibili Whisper
