## Current State (2026-11-26)
Pipeline modules and the Streamlit UI (`app.py`) are built on branch `feature/video-triage`. app.py has no unit tests (verified via Streamlit AppTest only); real-link end-to-end check is Task 9.

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
uv lock --upgrade-package yt-dlp && uv sync      # fix "YouTube changed" metadata errors
uv add <pkg>                                     # add a dependency
```

## Data model
One note per video (format TBD in spec): frontmatter (title, channel, url, source, date) + summary + transcript.

## Key patterns
- app.py is a thin UI layer; all logic lives in pipeline/notes. Current note path is `st.session_state["note"]`; summary failures are kept in `st.session_state["summary_error"]` to avoid retry loops until Regenerate.
- Status is stored in the note frontmatter (`unreviewed` / `watch` / `skip`).

## Known quirks
- No Docker: containers on macOS can't use Metal, so mlx-whisper would fall back to CPU.
- Bilibili CC subtitles often require login cookies; fall back to Whisper if unavailable.
- Bilibili subtitles arrive from yt-dlp as inline `data` (SRT text, no `url`); `CaptionTrack.data` carries it and `fetch_captions` returns it directly.
- `yt-dlp-ejs` is required for YouTube JS challenges (node solver script); it is a project dependency.
- Playlists, channels and multi-video links are rejected (single video only).
- Rolling-line dedupe applies only to auto captions; manual captions stay verbatim.
- Ollama's default context is short; use the `-64k` model variant for long transcripts.

## What's built / backlog
- [x] Environment
- [x] Pipeline modules + Streamlit UI
- [ ] End-to-end check with a real link (Task 9)
