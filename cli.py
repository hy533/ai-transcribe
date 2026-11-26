"""Command-line front end for agents and scripts (Pi, n8n, shell).

stdout carries only the result (JSON, or plain text for `read`); progress and
errors go to stderr. Exit 0 = success (a failed summary still counts: the note
is saved and `summary_error` says why), 1 = failure (JSON error on stderr).

  uv run python cli.py transcribe <url> [--force] [--no-summary]
  uv run python cli.py read <note.md> [--section summary|transcript]
  uv run python cli.py list [--status unreviewed|watch|skip] [--limit N]
  uv run python cli.py status <note.md> unreviewed|watch|skip
"""
import argparse
import json
import sys
from pathlib import Path

import config
from notes import list_recent, parse_note, set_status
from pipeline import Deps, PipelineError, ensure_summary, ensure_transcript, needs_summary

STATUSES = ["unreviewed", "watch", "skip"]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cli.py", description="Transcribe and summarise videos into the Obsidian library.")
    sub = p.add_subparsers(dest="command", required=True)
    t = sub.add_parser("transcribe", help="get (or reuse) the note for a link; prints JSON")
    t.add_argument("url")
    t.add_argument("--force", action="store_true", help="re-fetch the transcript even if a note exists")
    t.add_argument("--no-summary", action="store_true", help="skip the Ollama summary")
    r = sub.add_parser("read", help="print a note's summary or transcript")
    r.add_argument("path")
    r.add_argument("--section", choices=["summary", "transcript"], default="summary")
    ls = sub.add_parser("list", help="recent notes as JSON")
    ls.add_argument("--status", choices=STATUSES)
    ls.add_argument("--limit", type=int, default=config.SIDEBAR_LIMIT)
    s = sub.add_parser("status", help="set a note's status")
    s.add_argument("path")
    s.add_argument("status", choices=STATUSES)
    return p


def _transcribe(args, deps: Deps, vault: Path) -> dict:
    path, existed = ensure_transcript(args.url, vault, deps,
                                      lambda step, *_: print(f"step: {step}", file=sys.stderr, flush=True),
                                      force=args.force)
    summary_error = None
    if not args.no_summary and needs_summary(path):
        print("step: summary", file=sys.stderr, flush=True)
        try:
            ensure_summary(path, deps, lambda _chunk: None)
        except PipelineError as e:
            summary_error = e.message
    f = parse_note(path).fields
    return {"path": str(path), "title": f.get("title"), "source": f.get("source"),
            "language": f.get("language"), "transcript_source": f.get("transcript_source"),
            "status": f.get("status"), "existed": existed, "summary_error": summary_error}


def main(argv: list[str] | None = None, deps: Deps | None = None, vault: Path | None = None) -> int:
    args = _parser().parse_args(argv)
    vault = Path(vault or config.VAULT_DIR)
    try:
        if args.command == "transcribe":
            print(json.dumps(_transcribe(args, deps or Deps.real(), vault), ensure_ascii=False))
        elif args.command == "read":
            note = parse_note(Path(args.path))
            print((note.summary if args.section == "summary" else note.transcript).strip())
        elif args.command == "list":
            items = [i for i in list_recent(vault, 10_000) if not args.status or i.status == args.status]
            print(json.dumps([{"path": str(i.path), "title": i.title, "status": i.status}
                              for i in items[:args.limit]], ensure_ascii=False))
        elif args.command == "status":
            set_status(Path(args.path), args.status)
            print(json.dumps({"path": args.path, "status": args.status}, ensure_ascii=False))
    except PipelineError as e:
        print(json.dumps({"step": e.step, "error": e.message}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, ValueError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
