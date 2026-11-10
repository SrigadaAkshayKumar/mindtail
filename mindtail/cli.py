"""Command-line entry point: python -m mindtail <command> ..."""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

from . import ff, qc, samples
from .config import ROOT, SHORTS_DIR, TEMPLATES_DIR
from .spec import SpecError, load, missing_media


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def cmd_samples(a) -> int:
    made = samples.generate(force=a.force)
    print(f"Generated {len(made)} sample file(s) in {_rel(samples.SAMPLES)}" if made
          else f"Samples already present in {_rel(samples.SAMPLES)} (use --force to rebuild)")
    return 0


def cmd_new(a) -> int:
    if not re.fullmatch(r"MT-\d{4}", a.id):
        print("ID must look like MT-0001", file=sys.stderr)
        return 2
    slug = re.sub(r"[^a-z0-9]+", "-", a.slug.lower()).strip("-")
    dest = SHORTS_DIR / f"{a.id}-{slug}"
    if dest.exists() or any(SHORTS_DIR.glob(f"{a.id}-*")):
        print(f"A short with ID {a.id} already exists; not overwriting.", file=sys.stderr)
        return 1
    shutil.copytree(TEMPLATES_DIR / "short", dest)
    for f in dest.rglob("*"):
        if f.is_file() and f.suffix in {".md", ".yaml"}:
            text = f.read_text(encoding="utf-8")
            text = text.replace("{{ID}}", a.id).replace("{{TITLE}}", a.title or slug.replace("-", " "))
            text = text.replace("{{DATE}}", date.today().isoformat())
            f.write_text(text, encoding="utf-8")
    print(f"Created {_rel(dest)}")
    return 0


def cmd_check(a) -> int:
    spec = load(a.short)
    print(f"{spec.id} '{spec.title}': {len(spec.scenes)} scenes, {spec.duration:.1f}s, status {spec.status}")
    missing = missing_media(spec)
    for m in missing:
        print(f"  missing: {m}")
    if not missing:
        print("  all media present")
    return 0


def cmd_fetch(a) -> int:
    from .stock import fetch  # needs `requests`; imported lazily
    spec = load(a.short)
    for line in fetch(spec, refresh=a.refresh):
        print("  " + line)
    print(f"Provenance saved to {_rel(spec.lock_path)}")
    return 0


def cmd_render(a) -> int:
    from .render import render
    spec = load(a.short)
    out, warnings = render(spec, Path(a.out) if a.out else None, placeholder=a.placeholder,
                           preview=a.preview, verbose=a.verbose)
    for w in warnings:
        print(f"  warning: {w}")
    print(f"Rendered {_rel(out)}")
    if not a.no_qc:
        checks, report = qc.report(out, spec.target_lufs)
        qc.print_checks(checks)
        print(f"QC report: {_rel(report)}  (automatic checks only; watch the full video)")
    return 0


def cmd_qc(a) -> int:
    checks, report = qc.report(Path(a.video), a.lufs)
    qc.print_checks(checks)
    print(f"QC report: {_rel(report)}")
    return 1 if any(c.status == qc.FAIL for c in checks) else 0


def cmd_credits(a) -> int:
    from .stock import credits
    print(credits(load(a.short)) or "(no credits recorded)")
    return 0


def cmd_status(a) -> int:
    rows = []
    for spec_file in sorted(SHORTS_DIR.glob("*/spec.yaml")):
        try:
            s = load(spec_file)
            rows.append((s.id, s.status, f"{s.duration:.0f}s", s.title))
        except SpecError as e:
            rows.append((spec_file.parent.name, "INVALID", "-", str(e).splitlines()[1].strip()))
    if not rows:
        print("No shorts yet. Create one with: python -m mindtail new MT-0001 my-slug")
    for r in rows:
        print(f"{r[0]:<10} {r[1]:<16} {r[2]:>5}  {r[3]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mindtail", description="MINDTAIL Shorts pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("samples", help="generate synthetic test footage, music and sfx")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_samples)

    s = sub.add_parser("new", help="create a short folder from templates/short")
    s.add_argument("id", help="e.g. MT-0001")
    s.add_argument("slug", help="short name for the folder, e.g. phone-habit")
    s.add_argument("--title", default="")
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("check", help="validate a spec and list missing media")
    s.add_argument("short")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("fetch", help="download stock footage for scenes with a `query`")
    s.add_argument("short")
    s.add_argument("--refresh", action="store_true", help="search again even if already downloaded")
    s.set_defaults(func=cmd_fetch)

    s = sub.add_parser("render", help="render a short to MP4 and run QC")
    s.add_argument("short")
    s.add_argument("--out")
    s.add_argument("--preview", action="store_true", help="faster, lower-quality encode")
    s.add_argument("--placeholder", action="store_true", help="fill missing footage/audio with placeholders")
    s.add_argument("--no-qc", action="store_true")
    s.add_argument("-v", "--verbose", action="store_true", help="print ffmpeg commands")
    s.set_defaults(func=cmd_render)

    s = sub.add_parser("qc", help="run automatic checks on a video file")
    s.add_argument("video")
    s.add_argument("--lufs", type=float, default=-14.0)
    s.set_defaults(func=cmd_qc)

    s = sub.add_parser("credits", help="print footage/music credits for a short")
    s.add_argument("short")
    s.set_defaults(func=cmd_credits)

    s = sub.add_parser("status", help="list all shorts and their stage")
    s.set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (SpecError, ff.FFmpegError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # stock API errors etc.
        if e.__class__.__name__ in {"StockError", "HTTPError", "ConnectionError"}:
            print(f"error: {e}", file=sys.stderr)
            return 1
        raise
