# AI Transcribe

A personal, local-only tool for deciding whether a YouTube or Bilibili video is worth watching.

Paste a link and it:

1. Gets the full transcript. It uses the video's own captions when they exist; otherwise it downloads the audio and transcribes it locally with Whisper.
2. Writes a summary with a local Ollama model. Chinese videos get Chinese summaries, English videos get English ones.
3. Saves both as one markdown note in an Obsidian vault.

You then read the summary and transcript side by side and mark the video **Watch** or **Skip**. The Obsidian vault is the library; there is no separate database. Nothing leaves your Mac except the requests to YouTube or Bilibili.

---

## Requirements

| Need | Notes |
|---|---|
| Apple Silicon Mac | Whisper runs on the GPU through `mlx-whisper` (Metal). |
| [uv](https://docs.astral.sh/uv/) | Manages Python 3.12 and a project-local `.venv`. |
| Node.js on `PATH` | yt-dlp uses it to solve YouTube's JavaScript challenges. Homebrew Node works. The app checks for it at startup. |
| [Ollama](https://ollama.com) running at `localhost:11434` | With the model set in `config.py` (default `qwen3.8-27b-64k`). |
| An Obsidian vault folder | Set in `config.py` (`VAULT_DIR`). |

Disk: about 1.6 GB for the Whisper model, downloaded once on first use into the Hugging Face cache (`~/.cache/huggingface`). Audio files are temporary (see [Privacy and disk](#privacy-and-disk)).

## Setup

```bash
git clone https://github.com/hy533/ai-transcribe.git
cd ai-transcribe
uv sync
```

Then edit `config.py` for your machine (vault path, model name).

## Usage

```bash
uv run streamlit run app.py
```

This opens the app at http://localhost:8501.

- **Paste a link** and press Go. A progress box shows each step: reading video info, then captions or Whisper, then saving. The note is saved as soon as the transcript exists, and the summary streams in afterwards.
- **Library (sidebar):** your 30 most recent notes. The mark before each title is its status: `●` unreviewed, `✓` watch, `–` skip. Click a title to open it.
- **Watch / Skip:** changes only the `status:` line in the note's frontmatter.
- **⋯ menu:**
  - *Regenerate summary* clears the summary and writes a new one.
  - *Reprocess video* fetches the transcript again (asks first). It keeps your status and any sections you added in Obsidian.
- **Already processed:** pasting a link you already have opens the existing note, with an "Already in your library" banner. It doesn't download anything again.
- **Interrupted summary:** if you click away while a summary is being written, the note keeps an empty Summary section. It is generated again the next time you open the note.

Supported links: single YouTube videos and single Bilibili videos. Playlists and channels are rejected with an error.

## Note format

One file per video, named `<title> [<video_id>].md`:

```markdown
---
title: ...
channel: ...
url: https://www.youtube.com/watch?v=...
video_id: ...
source: youtube            # or bilibili
published: '2026-11-22'
duration: '13:38'
processed: '2026-11-26'
language: en               # transcript language (zh, en, ...)
transcript_source: captions  # or whisper
status: unreviewed         # unreviewed | watch | skip
tags:
- video
---

## Summary

A short paragraph, then **Key points** bullets, then **Who it's for:**.

## Transcript
[00:12] One line per ~30 seconds of speech...
```

The app finds a note by `video_id` in the frontmatter, not by filename, so you can rename notes in Obsidian. Edits are made in place, one line or one section at a time, so your own edits and extra sections survive.

## Privacy and disk

- Only the audio track is downloaded, never the video. It goes into a temporary folder that is deleted as soon as Whisper finishes, before you decide Watch or Skip. Videos with captions download no media at all.
- Transcription (Whisper) and summarising (Ollama) both run locally.
- Streamlit usage stats are off (`.streamlit/config.toml`).
- The only file that stays is the markdown note. The Whisper model stays in the Hugging Face cache so the next video doesn't download it again.

## Project layout

```
app.py           Streamlit UI only (sidebar, header, summary/transcript columns)
pipeline.py      ensure_transcript / ensure_summary orchestration (Deps injected for tests)
fetch.py         yt-dlp metadata/captions/audio, Whisper, PipelineError, Node check
captions.py      pick a caption track, parse VTT/SRT/JSON captions
transcript.py    segments -> timestamped markdown, language normalising
summarize.py     Ollama streaming summary, context-fit check, <think> stripping
notes.py         note format: write/parse/find, set_status, replace_section, list_recent
config.py        vault path, model, limits
tests/           pytest (live tests marked `live`)
docs/superpowers/  design spec and implementation plan
```

Flow:

```
link → video info ─ note exists? ─yes→ open it
                    │ no
                    ├─ captions? ─yes→ download + parse captions ─┐
                    │ no (or caption fetch fails)                 │
                    └─ download audio → Whisper ──────────────────┤
                                                                  ▼
                                            save note → stream summary into note
```

## Tests

```bash
uv run pytest            # offline unit tests (no network, no model)
uv run pytest -m live    # live tests against the local Ollama model
```

`app.py` has no unit tests; check UI changes by running the app.

---

## Maintenance notes

Most breakage comes from YouTube or Bilibili changing their sites. The fixes, from most to least likely:

### "Couldn't read video info" / YouTube errors

YouTube changes often, and yt-dlp releases fixes within days. Upgrade it:

```bash
uv lock --upgrade-package yt-dlp && uv sync
```

If that isn't enough, also upgrade the JavaScript challenge solver:

```bash
uv lock --upgrade-package yt-dlp-ejs && uv sync
```

To check whether yt-dlp itself works outside the app:

```bash
uv run yt-dlp -F "<link>"
```

If a fix only exists in yt-dlp's nightly build, test it without changing the project:

```bash
uvx --from "yt-dlp[default]" --prerelease allow yt-dlp -F "<link>"
```

### "Node isn't installed" / JS challenge errors

yt-dlp needs `node` on `PATH`. Check with `node --version`. Reinstall with `brew install node` if needed.

### Bilibili

- **Audio download fails with HTTP 567 or 403:** Bilibili's CDN refuses one whole-file request. `download_audio` in `fetch.py` downloads in 10 MB pieces (`http_chunk_size`) for this reason; don't remove it.
- **Subtitles are never used:** Bilibili only shows CC subtitles to logged-in users, so most Bilibili videos go through Whisper. To use them, set `COOKIES_BROWSER = "chrome"` (or `"safari"`, `"firefox"`) in `config.py`; yt-dlp will then read your Bilibili login from that browser. This also unlocks higher-quality formats.
- **Old videos rejected as playlists:** some old Bilibili uploads come back from yt-dlp as multi-part, and the app rejects them with the playlist message. This is a known limitation.

### Ollama / summary problems

- **"Ollama isn't running":** start Ollama, then use ⋯ → Regenerate summary. The transcript is already saved.
- **"Transcript is too long":** the transcript is longer than the model's context (`NUM_CTX` in `config.py`, 64k tokens, minus 4k for the reply). Use a model with a bigger context, or summarise the saved transcript some other way.
- **Changing the model:** set `MODEL` in `config.py` to a name from `ollama list`. Use a variant with a large context window; Ollama's default context is too short for long videos. Then run `uv run pytest -m live` to check summaries still come back in the right language and shape.
- Summaries can't contain markdown headings: any `#` heading the model writes is turned into bold text, so it can't split the note into extra sections.

### Whisper

- The model is `WHISPER_MODEL` in `config.py`. It downloads into `~/.cache/huggingface` on first use (~1.6 GB). To free the space, delete the model from that cache; it will download again when next needed.
- Whisper sometimes writes Chinese in Traditional characters. The summary is still in Simplified Chinese.
- Don't run this in Docker: containers on macOS can't use Metal, so Whisper would fall back to the much slower CPU.

### Dependencies

```bash
uv sync                          # install exactly what uv.lock says
uv add <package>                 # add a dependency
uv lock --upgrade && uv sync     # upgrade everything (then run the tests)
```

After any upgrade, run `uv run pytest`, then process one captioned YouTube video and one Bilibili video in the app.

### Known quirks

- In Chinese summaries the "Key points" and "Who it's for" labels stay in English, and the model sometimes leaves out "Who it's for".
- A line starting with `#hashtag` in a summary is shown in bold.
- A `$...$` in a video title can display as math in the app's header.
- At narrow window widths the Watch/Skip buttons shrink to single letters.

### Changing the code

- Keep `app.py` a thin UI layer; logic goes in `pipeline.py` and `notes.py`, where it can be tested with the fakes in `tests/test_pipeline.py`.
- Never keep downloaded media: audio goes to a `TemporaryDirectory` that is deleted right after transcription.
- Edit notes in place (`set_field`, `set_status`, `replace_section`); never rewrite a whole note, or the user's Obsidian edits are lost.
- `CLAUDE.md` has the working notes for coding with Claude Code, and `docs/superpowers/` has the original design spec and plan.
