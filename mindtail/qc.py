"""Automatic technical checks on a rendered Short.

These cover the measurable part of the QC checklist (format, length, audio
level, black frames, silences). Watching the full video is still required:
see templates/qc-checklist.md.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from . import ff
from .config import AUDIO_RATE, FPS, HEIGHT, TARGET_LUFS, WIDTH

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _fps(rate: str) -> float:
    num, _, den = rate.partition("/")
    return float(num) / float(den or 1) if float(den or 1) else 0.0


def analyze(path: Path, target_lufs: float = TARGET_LUFS) -> list[Check]:
    ff.require()
    info = ff.probe(path)
    checks: list[Check] = []
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"].get("duration") or 0)
    size_mb = int(info["format"].get("size") or 0) / 1_000_000

    if v is None:
        return [Check("video stream", FAIL, "no video stream")]
    w, h = int(v["width"]), int(v["height"])
    checks.append(Check("resolution", PASS if (w, h) == (WIDTH, HEIGHT) else FAIL, f"{w}x{h}"))
    fps = _fps(v.get("avg_frame_rate", "0/1"))
    checks.append(Check("frame rate", PASS if abs(fps - FPS) < 0.05 else WARN, f"{fps:.2f} fps"))
    ok_codec = v.get("codec_name") == "h264" and v.get("pix_fmt") == "yuv420p"
    checks.append(Check("video codec", PASS if ok_codec else WARN, f"{v.get('codec_name')} {v.get('pix_fmt')}"))

    if dur > 180:
        checks.append(Check("duration", FAIL, f"{dur:.1f}s (Shorts max is 3 minutes)"))
    elif dur < 15 or dur > 90:
        checks.append(Check("duration", WARN, f"{dur:.1f}s (MINDTAIL target is roughly 15-90s)"))
    else:
        checks.append(Check("duration", PASS, f"{dur:.1f}s"))

    if a is None:
        checks.append(Check("audio stream", FAIL, "no audio stream"))
    else:
        rate = int(a.get("sample_rate") or 0)
        checks.append(Check("audio stream", PASS if rate == AUDIO_RATE else WARN,
                            f"{a.get('codec_name')} {rate} Hz {a.get('channels')}ch"))

    af = ["silencedetect=n=-45dB:d=1.5"] if a else []
    if a:
        af.append(f"loudnorm=I={target_lufs}:print_format=json")
    args = ["-i", str(path), "-vf", "blackdetect=d=0.25:pix_th=0.08"]
    args += ["-af", ",".join(af)] if af else ["-an"]
    stderr = ff.run(args + ["-f", "null", "-"])

    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", stderr)
    if blacks:
        spans = ", ".join(f"{float(s):.2f}-{float(e):.2f}s" for s, e in blacks[:5])
        checks.append(Check("black frames", WARN, f"{len(blacks)} span(s): {spans} (check: very dark footage can trigger this)"))
    else:
        checks.append(Check("black frames", PASS, "none"))

    if a:
        silences = re.findall(r"silence_start: ([\d.]+)", stderr)
        checks.append(Check("silence gaps", WARN if silences else PASS,
                            f"{len(silences)} gap(s) over 1.5s at " + ", ".join(f"{float(s):.1f}s" for s in silences[:5])
                            if silences else "none over 1.5s"))
        m = ff.parse_loudnorm(stderr)
        try:
            lufs, tp = float(m["input_i"]), float(m["input_tp"])
        except ValueError:
            checks.append(Check("loudness", WARN, "audio is silent"))
        else:
            status = PASS if abs(lufs - target_lufs) <= 1.5 else WARN
            checks.append(Check("loudness", status, f"{lufs:.1f} LUFS integrated (target {target_lufs})"))
            checks.append(Check("true peak", PASS if tp <= -1.0 else WARN, f"{tp:.1f} dBTP (keep at or below -1.0)"))

    checks.append(Check("file size", PASS, f"{size_mb:.1f} MB"))
    return checks


def report(path: Path, target_lufs: float = TARGET_LUFS) -> tuple[list[Check], Path]:
    checks = analyze(path, target_lufs)
    out = path.with_suffix(".qc.json")
    worst = FAIL if any(c.status == FAIL for c in checks) else WARN if any(c.status == WARN for c in checks) else PASS
    out.write_text(json.dumps({"file": path.name, "result": worst, "checks": [asdict(c) for c in checks],
                               "note": "Automatic checks only. Watch the full video before approving."},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    return checks, out


def print_checks(checks: list[Check]) -> None:
    for c in checks:
        print(f"  [{c.status}] {c.name}: {c.detail}")
