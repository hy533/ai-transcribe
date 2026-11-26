# Apple Podcasts support — design (short)

Status: approved 2026-11-26.

## Intent

The user listens to podcasts on Apple Podcasts and wants to triage episodes the same way as videos: paste an episode link → full transcript → summary in the episode's language → one note in the Obsidian library → Watch/Skip. Apple Podcasts is the only podcast source wanted.

## Goals / non-goals / anti-goals

- Goal: an Apple Podcasts *episode* link works end to end, exactly like a YouTube/Bilibili link.
- Non-goals: other podcast apps (Spotify is DRM; Xiaoyuzhou, Ximalaya, RSS not wanted), whole-show import, subscriptions/new-episode watching, chunked summarisation of very long episodes.
- Anti-goals: keeping audio files; a separate podcast UI or library; breaking existing video notes.

## Recon (2026-11-26, yt-dlp 2026.11.23)

- Episode URL `https://podcasts.apple.com/<cc>/podcast/<slug>/id<showId>?i=<episodeId>` → extractor `ApplePodcasts`; `id` = episodeId; `title`; `series` = show name; `uploader`/`channel` = None; `duration`; `upload_date`; no subtitles; audio downloads as mp3 (no CDN blocking).
- Show URL (no `?i=`) → yt-dlp falls back to generic and raises "Unsupported URL".
- Summary context budget (64k − 4k): measured ~330 chars/min Chinese, ~1000 chars/min (≈250 tokens) English → limit ≈ 3 h Chinese, ≈ 4 h English. Longer episodes hit the existing "too long" error; transcript still saved.

## Approaches

1. **Third source in the existing pipeline** (chosen): extend `source_of`, `build_meta`, note tags and UI copy. Smallest change; same library, notes and tests.
2. Separate podcast pipeline/module: duplicates fetch/transcribe/save for no gain.
3. Generic "any yt-dlp audio site": wider than asked; untested sources would fail in confusing ways.

## Design

- `fetch.source_of`: extractor key containing `applepodcasts` → `"apple_podcasts"`. Error text for unknown sites: "Only YouTube, Bilibili and Apple Podcasts links are supported."
- `fetch.build_meta`: `channel` falls back to `info["series"]` (after `channel`, `uploader`). `video_id` = yt-dlp `id` (episode id).
- Show-link guard: before calling `get_info`, if the URL host is `podcasts.apple.com` and has no `i` query parameter → `PipelineError("metadata", "That's a show page — open an episode and copy its link.")`.
- No captions → Whisper path (already the behaviour when `pick_caption_track` returns None).
- Notes: `tags: [podcast]` when `source == "apple_podcasts"`, else `[video]`. Same folder (`VAULT_DIR`), same filename rule, same frontmatter keys.
- UI: `SOURCE_NAMES["apple_podcasts"] = "Apple Podcasts"`; link placeholder "Paste a YouTube, Bilibili or Apple Podcasts link". Watch/Skip labels and status values unchanged.
- Media: audio in `TemporaryDirectory`, deleted right after transcription (unchanged rule).
- Docs: README (supported links, note example, maintenance) and CLAUDE.md.

## UI decisions (gstack design review, 2026-11-26)

- **D1 Whisper wait line (all sources):** when the episode/video duration is known, the Whisper step reads `Transcribing <h:mm:ss or mm:ss> of audio with Whisper (about N min)…`, with N = max(1, round(duration_seconds / 2100)) (measured ≈ 1 min per 35 min of audio on this Mac, model already cached). Unknown duration → current line unchanged. The first-download line (`whisper-download`) stays as is.
- **D2 Buttons:** keep `Watch` / `Skip` for podcasts too (user choice: identical everywhere).
- **D3 Library:** no podcast marker in the sidebar; the header meta line (`<show> · <duration> · Apple Podcasts · whisper`) and the `podcast` tag are enough.
- Header meta line for podcasts shows the show name where videos show the channel (falls out of `channel` = `series`).
- Error copy: show link → "That's a show page — open an episode and copy its link."; unknown site → "Only YouTube, Bilibili and Apple Podcasts links are supported."

### Interaction states

| Feature | Loading | Error | Success |
|---|---|---|---|
| Paste episode link | status box: Reading info → Transcribing <len> (about N min) → saved | red error inside expanded "Failed" box, link stays in the box | note opens; summary streams |
| Paste show link | — | "That's a show page — open an episode and copy its link." | — |
| Episode > ~3 h (zh) / ~4 h (en) | — | existing "too long" summary error; transcript saved | — |

### Not in scope (design)

- Podcast artwork in the header; per-source styling; a podcast marker in the Library (D3).

## Tests

- Whisper step line includes duration + estimate when duration known; unchanged when unknown.
- `source_of` → `apple_podcasts` for extractor key `ApplePodcasts`.
- `build_meta` uses `series` as channel when channel/uploader missing.
- Show URL (no `i=`) raises the show-page error without calling `get_info`.
- New note for apple_podcasts has `tags: [podcast]`; video notes keep `[video]`.
- Live/E2E: one real Apple Podcasts episode through the app.

## Left to the builder

Exact placement of the show-link check (pipeline vs fetch), test fixture shapes.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAR (FULL) | score: 6/10 → 9/10, 3 decisions |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | — | not run for this spec |

- **UNRESOLVED:** 0
- **VERDICT:** Design CLEARED; eng review not run for this spec.
