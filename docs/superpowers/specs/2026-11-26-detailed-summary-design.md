# Detailed summary on demand — design (short)

Status: approved 2026-11-26.

## Intent

The short summary is good for deciding whether to watch, but it drops the story/plot and the concrete information (names, numbers, dates, claims, conclusions). Sometimes the user wants that captured. They want both kept in the note: the short one for triage, the detailed one as a record of the content.

## Goals / non-goals / anti-goals

- Goal: on any note, one click writes a detailed summary that follows the video in order and keeps the concrete facts; it is saved in the note next to the short summary.
- Non-goals: a "shorter than today" level; generating detail automatically for every video; timestamps or links inside the detailed summary; chunking for transcripts that don't fit the context.
- Anti-goals: changing or replacing the short summary; slowing down normal triage; losing the user's Obsidian edits.

## Approaches

1. **On demand (chosen):** a button per note generates the detailed summary when wanted. Costs ~20–60 s only for videos the user cares about.
2. Automatic for every video: always ready, but every video (including skipped ones) takes noticeably longer and keeps the GPU busy.
3. Separate detailed-summary files: splits one video across two notes. Rejected.

## Design

**Prompt** (`summarize.py`, alongside the existing one; same model, language rule, think-stripping and streaming):
- 1–2 sentence overview.
- Then the content in the order the video presents it, as 3–8 parts, each starting with a bold label line `**<short part title>**` followed by a short paragraph or bullets. For stories: what happens, who is involved, how it turns and ends. For talks/explainers: each argument or step with its evidence.
- Keep concrete details: names, numbers, dates, places, prices, results, and the speaker's actual conclusions. Short quotes only when the exact words matter.
- End with `**Takeaways**` and 3–6 bullets.
- No `#` headings (same rule and the same heading-to-bold demotion as the short summary). Written in the video's language. Summarize, don't translate or transcribe.

**Note**: new section `## Detailed summary`, placed between `## Summary` and `## Transcript` (inserted before `## Transcript` when missing). Only that section is ever written by this feature. Frontmatter unchanged.

**Pipeline**: `ensure_detailed_summary(path, deps, on_chunk)` mirrors `ensure_summary`: same context check and error messages, writes the section only after the stream completes (an interrupted run saves nothing; the button stays). `needs_summary` keeps ignoring the detailed section, so nothing auto-generates it.

**UI** (summary column):
- Two tabs: **Summary** | **Detailed**.
- Detailed tab, empty: one line "Follows the video in order and keeps names, numbers and the plot." plus a button **Write detailed summary**. While running: the text streams in, same as the short summary.
- Detailed tab, filled: the detailed summary.
- ⋯ menu gains **Regenerate detailed summary** (shown only when one exists). The existing "Regenerate summary" only rewrites the short one.
- Errors (Ollama down, too long, empty result) show in the Detailed tab in red with the same wording as the short summary; the short summary is unaffected.
- **Reprocess video** clears the detailed summary too (it described the old transcript); the user can write it again.

## Tests

- Detailed prompt contains the language rule, the ordering/concrete-details instructions, `**Takeaways**`, and the no-headings rule.
- `ensure_detailed_summary` writes `## Detailed summary` between Summary and Transcript; leaves the short summary and user sections untouched; demotes headings; raises the same `PipelineError`s as `ensure_summary` (Ollama down, too long).
- A failed/interrupted stream leaves the note unchanged.
- Reprocess empties the detailed section; Regenerate summary doesn't touch it.
- `needs_summary` is false when only the detailed section is empty.
- Live (`-m live`): one real detailed summary in Chinese and one in English.

## Left to the builder

Exact prompt wording within the rules above; how `Note` exposes the new section; Streamlit widget keys.
