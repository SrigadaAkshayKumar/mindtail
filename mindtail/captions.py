"""Build an ASS subtitle file for the on-screen text and its animations.

ffmpeg's `ass` filter (libass + HarfBuzz) shapes Devanagari correctly, which
plain `drawtext` does not. Latin words (Hinglish) are switched to Noto Sans
automatically, because Noto Sans Devanagari has no Latin letters.
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import FONT_HINDI, FONT_LATIN, HEIGHT, WIDTH
from .spec import Spec, TextItem

# ASS colours are &HAABBGGRR
WHITE = "&H00FFFFFF&"
BLACK = "&H00000000&"
HIGHLIGHT = {
    "cyan": "&H00FFE500&",    # #00E5FF electric cyan (brand)
    "yellow": "&H0000D7FF&",  # #FFD700 (use sparingly)
    "red": "&H003B30FF&",     # #FF303B (use sparingly)
    "white": WHITE,
}

# x is slightly left of centre to stay clear of the Shorts action buttons.
X = 520
Y = {"upper": 560, "center": 900, "lower": 1300}

# Name, Fontsize, Primary, Outline, Back, BorderStyle, Outline, Shadow
STYLES = {
    "hook":    (118, "&H00FFFFFF", "&H00000000", "&H96000000", 1, 8, 3),
    "caption": (86,  "&H00FFFFFF", "&H00000000", "&H96000000", 1, 6, 2),
    "small":   (58,  "&H00FFFFFF", "&H00000000", "&H96000000", 1, 4, 2),
    # black text on a cyan box, for labels like "PART 2" or "FACT #3"
    "tag":     (58,  "&H00000000", "&H00FFE500", "&H00FFE500", 3, 14, 0),
}
STYLE_TEXT_COLOUR = {"hook": WHITE, "caption": WHITE, "small": WHITE, "tag": BLACK}

LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z'’]*")


def _ts(seconds: float) -> str:
    cs = max(0, int(round(seconds * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _clean(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")")


def _fonts(token: str) -> str:
    """Wrap Latin-letter runs so they render in the Latin font."""
    out, pos = [], 0
    for m in LATIN_RUN.finditer(token):
        out.append(token[pos:m.start()])
        out.append(f"{{\\fn{FONT_LATIN}}}{m.group()}{{\\fn{FONT_HINDI}}}")
        pos = m.end()
    out.append(token[pos:])
    return "".join(out)


def _norm(word: str) -> str:
    return re.sub(r"[^\wऀ-ॿ]", "", word).lower()


def _tokens(item: TextItem) -> list[list[tuple[str, bool]]]:
    """Lines of (word, highlighted) pairs."""
    lines = [ln.split() for ln in _clean(item.content).splitlines() if ln.strip()]
    flat = [w for ln in lines for w in ln]
    marked = [False] * len(flat)
    for phrase in item.highlight:
        target = [_norm(w) for w in phrase.split() if _norm(w)]
        n = len(target)
        if not n:
            continue
        for i in range(len(flat) - n + 1):
            if [_norm(w) for w in flat[i:i + n]] == target:
                for k in range(i, i + n):
                    marked[k] = True
    out, k = [], 0
    for ln in lines:
        row = []
        for w in ln:
            row.append((w, marked[k]))
            k += 1
        out.append(row)
    return out


def _body(item: TextItem, dur_ms: int) -> str:
    base = STYLE_TEXT_COLOUR[item.style]
    hl = HIGHLIGHT[item.highlight_color]
    lines = _tokens(item)
    n_words = sum(len(ln) for ln in lines)
    # word-by-word reveal: spread the reveal over the first ~60% of the item
    step = min(180, int(dur_ms * 0.6 / max(1, n_words)))
    parts_lines, idx = [], 0
    for ln in lines:
        parts = []
        for word, marked in ln:
            tag = ""
            if item.animation == "words":
                t0 = idx * step
                tag += f"\\alpha&HFF&\\t({t0},{t0 + 80},\\alpha&H00&)"
            if marked:
                tag += f"\\c{hl}"
            elif item.animation == "words" or idx:
                tag += f"\\c{base}"
            word = _fonts(word)
            parts.append(f"{{{tag}}}{word}" if tag else word)
            idx += 1
        parts_lines.append(" ".join(parts))
    return "\\N".join(parts_lines)


def _animation(item: TextItem, dur_ms: int) -> str:
    y = Y[item.position]
    pos = f"\\an5\\pos({X},{y})"
    out_ms = min(120, dur_ms // 4)
    a = item.animation
    if a == "pop":
        return f"{pos}\\fad(60,{out_ms})\\fscx70\\fscy70\\t(0,90,\\fscx108\\fscy108)\\t(90,170,\\fscx100\\fscy100)"
    if a == "punch":
        return f"{pos}\\fad(0,{out_ms})\\fscx135\\fscy135\\t(0,130,\\fscx100\\fscy100)"
    if a == "fade":
        return f"{pos}\\fad({min(220, dur_ms // 3)},{min(200, dur_ms // 3)})"
    if a == "slide_up":
        return f"\\an5\\move({X},{y + 90},{X},{y},0,220)\\fad(120,{out_ms})"
    if a == "words":
        return f"{pos}\\fad(0,{out_ms})"
    return pos


def build_ass(spec: Spec) -> str:
    header = [
        "[Script Info]",
        f"Title: {spec.id}",
        "ScriptType: v4.00+",
        f"PlayResX: {WIDTH}",
        f"PlayResY: {HEIGHT}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    for name, (size, prim, outl, back, border, outline, shadow) in STYLES.items():
        header.append(
            f"Style: {name},{FONT_HINDI},{size},{prim},&H000000FF,{outl},{back},"
            f"-1,0,0,0,100,100,0,0,{border},{outline},{shadow},5,90,150,0,1"
        )
    header += ["", "[Events]",
               "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    events = []
    for scene, start in zip(spec.scenes, spec.scene_starts()):
        for layer, item in enumerate(scene.text):
            t0, t1 = start + item.start, start + item.end
            dur_ms = int((t1 - t0) * 1000)
            text = f"{{{_animation(item, dur_ms)}}}{_body(item, dur_ms)}"
            events.append(f"Dialogue: {layer},{_ts(t0)},{_ts(t1)},{item.style},,0,0,0,,{text}")
    return "\n".join(header + events) + "\n"


def write_ass(spec: Spec, path: Path) -> Path:
    path.write_text(build_ass(spec), encoding="utf-8")
    return path
