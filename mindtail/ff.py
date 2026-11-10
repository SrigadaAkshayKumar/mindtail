"""Small helpers around the ffmpeg / ffprobe command-line tools."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise FFmpegError(f"`{tool}` not found on PATH. Install ffmpeg (with libass) first.")


def run(args: list[str], cwd: Path | None = None, verbose: bool = False) -> str:
    """Run ffmpeg with args; return stderr (where ffmpeg writes its analysis output)."""
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", *args]
    if verbose:
        print("  $ " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-25:])
        raise FFmpegError(f"ffmpeg failed ({proc.returncode}):\n{tail}")
    return proc.stderr


def probe(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe could not read {path}: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def duration(path: Path) -> float:
    info = probe(path)
    return float(info.get("format", {}).get("duration") or 0.0)


def filter_path(path: Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument."""
    s = str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f"'{s}'"


def parse_loudnorm(stderr: str) -> dict:
    """Extract the JSON block printed by loudnorm=print_format=json."""
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end < start:
        raise FFmpegError("could not find loudnorm measurement in ffmpeg output")
    return json.loads(stderr[start:end + 1])
