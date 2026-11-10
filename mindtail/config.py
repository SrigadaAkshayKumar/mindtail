"""Project-wide paths and render constants."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "assets" / "fonts"
LIBRARY_DIR = ROOT / "library"
SHORTS_DIR = ROOT / "shorts"
TEMPLATES_DIR = ROOT / "templates"

# YouTube Shorts canvas
WIDTH = 1080
HEIGHT = 1920
FPS = 30
AUDIO_RATE = 48000

# Fonts bundled in assets/fonts (SIL OFL 1.1)
FONT_HINDI = "Noto Sans Devanagari"  # Devanagari + digits/punctuation, no Latin letters
FONT_LATIN = "Noto Sans"             # used automatically for English/Hinglish words

# Loudness targets for the final mix
TARGET_LUFS = -14.0
TRUE_PEAK = -1.5
LRA = 11.0


def load_env(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env into os.environ (existing vars win)."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)
