from pathlib import Path

import streamlit as st

import config
from fetch import PipelineError, check_node
from notes import list_recent, parse_note, replace_section, set_status
from pipeline import Deps, ensure_summary, ensure_transcript, needs_summary

STEP_LINES = {
    "metadata": "Reading video info…",
    "captions": "Using the video's captions…",
    "whisper": "Transcribing audio with Whisper…",
    "whisper-download": "First-time Whisper model download (~1.6 GB)…",
}
STATUS_MARKS = {"unreviewed": "● ", "watch": "✓ ", "skip": "– "}
SOURCE_NAMES = {"youtube": "YouTube", "bilibili": "Bilibili"}


def process_link(url: str, force: bool = False):
    """Run ensure_transcript inside an st.status; returns (path, existed) or None on error."""
    with st.status("Working…", expanded=True) as status:
        def on_step(step: str) -> None:
            if step == "saved":
                return
            st.write(STEP_LINES[step])
        try:
            path, existed = ensure_transcript(url, config.VAULT_DIR, Deps.real(), on_step, force=force)
        except PipelineError as e:
            status.update(label="Failed", state="error")
            st.error(f"{e.step}: {e.message}")
            return None
        status.update(label=f"Saved → {path.name}", state="complete", expanded=False)
    return path, existed


def render_sidebar() -> None:
    st.sidebar.header("Library")
    items = list_recent(config.VAULT_DIR, config.SIDEBAR_LIMIT)
    if not items:
        st.sidebar.caption("No videos yet.")
    for item in items:
        title = item.title if len(item.title) <= 40 else item.title[:40] + "…"
        mark = STATUS_MARKS.get(item.status, "● ")
        if st.sidebar.button(mark + title, key=str(item.path), use_container_width=True):
            st.session_state["note"] = item.path
            st.rerun()


@st.dialog("Reprocess video")
def reprocess_dialog(url: str) -> None:
    st.write("Replaces transcript and summary; keeps your status and notes.")
    if st.button("Reprocess", type="primary"):
        if process_link(url, force=True):
            st.rerun()


def render_header(path: Path, note) -> None:
    fields = note.fields
    left, right = st.columns([12, 1])
    left.markdown(f"### [{fields.get('title')}]({fields.get('url')})")
    with right.popover("⋯"):
        if st.button("Regenerate summary"):
            st.session_state.get("summary_error", {}).pop(str(path), None)
            replace_section(path, "Summary", "")
            st.rerun()
        if st.button("Reprocess video"):
            reprocess_dialog(str(fields.get("url")))
    source = SOURCE_NAMES.get(str(fields.get("source")), str(fields.get("source")))
    st.caption(" · ".join(str(x) for x in (
        fields.get("channel"), fields.get("duration"), source, fields.get("transcript_source"))))

    status = str(fields.get("status", "unreviewed"))
    watch, skip, label, _ = st.columns([1, 1, 2, 8])
    for col, choice in ((watch, "watch"), (skip, "skip")):
        if col.button(choice.capitalize(), key=f"mark-{choice}",
                      type="primary" if status == choice else "secondary"):
            try:
                set_status(path, choice)
            except OSError as e:
                st.toast(f"Couldn't save status: {e}", icon="❌")
            else:
                st.toast(f"Marked as {choice}")
                st.rerun()
    label.caption(f"status: {status}")


def render_columns(path: Path, note) -> None:
    summary_col, transcript_col = st.columns([2, 3])
    errors = st.session_state.setdefault("summary_error", {})
    with summary_col:
        st.subheader("Summary")
        if str(path) in errors:
            st.warning("Summary failed — use ⋯ → Regenerate")
            st.error(errors[str(path)])
        elif needs_summary(path):
            placeholder = st.empty()
            buffer = ""

            def on_chunk(chunk: str) -> None:
                nonlocal buffer
                buffer += chunk
                placeholder.markdown(buffer)
            try:
                ensure_summary(path, Deps.real(), on_chunk)
            except PipelineError as e:
                errors[str(path)] = f"{e.step}: {e.message}"
            st.rerun()
        else:
            st.markdown(note.summary)
    with transcript_col:
        st.subheader("Transcript")
        with st.container(height=650):
            st.markdown(note.transcript)


def main() -> None:
    st.set_page_config(page_title="Video Triage", layout="wide")
    try:
        check_node()
    except PipelineError as e:
        st.error(f"{e.step}: {e.message}")
        st.stop()
    if not config.VAULT_DIR.is_dir():
        st.error(f"Vault folder not found: {config.VAULT_DIR}")
        st.stop()

    with st.form("go", clear_on_submit=False):
        box, go = st.columns([8, 1], vertical_alignment="bottom")
        url = box.text_input("Link", placeholder="Paste a YouTube or Bilibili link",
                             label_visibility="collapsed")
        submitted = go.form_submit_button("Go")
    if submitted and url.strip():
        result = process_link(url.strip())
        if result:
            path, existed = result
            st.session_state["note"] = path
            if existed:
                processed = parse_note(path).fields.get("processed")
                st.info(f"Already in your library (processed {processed})")

    render_sidebar()
    path = st.session_state.get("note")
    if path is None or not Path(path).exists():
        st.write("Paste a link to get its transcript and summary.")
        return
    note = parse_note(path)
    render_header(path, note)
    render_columns(path, note)


main()
