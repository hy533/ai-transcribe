## Current State (2026-11-26)
Environment is set up (uv, Python 3.12, deps installed). No app code yet. Next: brainstorm → spec → plan for the paste-link → transcript → summary → Obsidian note pipeline.

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
pyproject.toml   # deps (managed by uv)
uv.lock          # locked versions
.python-version  # 3.12
CLAUDE.md        # this file
```

## Dev commands
```bash
uv sync                 # install/refresh deps
uv run pytest           # tests
uv add <pkg>            # add a dependency
```

## Data model
One note per video (format TBD in spec): frontmatter (title, channel, url, source, date) + summary + transcript.

## Key patterns
TBD after spec.

## Known quirks
- No Docker: containers on macOS can't use Metal, so mlx-whisper would fall back to CPU.
- Bilibili CC subtitles often require login cookies; fall back to Whisper if unavailable.
- Ollama's default context is short; use the `-64k` model variant for long transcripts.

## What's built / backlog
- [x] Environment
- [ ] Pipeline + UI (MVP)
