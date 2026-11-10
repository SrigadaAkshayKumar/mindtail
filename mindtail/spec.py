"""Load and validate a Short spec (shorts/<ID>-<slug>/spec.yaml).

A spec describes one Short as a list of timed scenes. Each scene has a
footage source, optional on-screen text and optional sound effects. The
background music and (later) the voiceover run across the whole video.
See docs/spec-reference.md for the full format.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import ROOT, TARGET_LUFS

STATUSES = [
    "IDEA", "SELECTED", "RESEARCHED", "SCRIPT_DRAFT", "SCRIPT_APPROVED",
    "VOICE_READY", "VISUALS_READY", "EDITED", "QC_APPROVED", "UPLOAD_READY",
    "PUBLISHED", "ANALYZED",
]
TEXT_STYLES = {"hook", "caption", "small", "tag"}
ANIMATIONS = {"pop", "punch", "fade", "slide_up", "words", "none"}
POSITIONS = {"upper", "center", "lower"}
HIGHLIGHT_COLORS = {"cyan", "yellow", "red", "white"}
MOTIONS = {"none", "zoom_in", "zoom_out"}
TRANSITIONS = {"cut", "flash", "fade"}
PROVIDERS = {"pexels", "pixabay"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


class SpecError(ValueError):
    """Raised with every problem found in a spec, one per line."""


@dataclass
class TextItem:
    content: str
    start: float          # seconds, relative to the scene start
    end: float            # seconds, relative to the scene start
    style: str = "caption"
    animation: str = "pop"
    position: str = "center"
    highlight: list[str] = field(default_factory=list)
    highlight_color: str = "cyan"


@dataclass
class Sfx:
    file: str
    at: float             # seconds, relative to the scene start
    volume_db: float = 0.0


@dataclass
class Footage:
    file: str | None = None
    query: str | None = None
    provider: str = "pexels"
    pick: int = 0         # 0 = best match, 1 = second best, ...
    start: float = 0.0    # seconds into the source clip


@dataclass
class Scene:
    index: int
    duration: float
    footage: Footage
    motion: str = "none"
    transition: str = "cut"
    grade: bool = True
    text: list[TextItem] = field(default_factory=list)
    sfx: list[Sfx] = field(default_factory=list)
    note: str = ""


@dataclass
class Bgm:
    file: str
    volume_db: float = -16.0
    offset: float = 0.0
    fade_in: float = 0.3
    fade_out: float = 1.5


@dataclass
class Voice:
    file: str
    volume_db: float = 0.0
    duck_bgm: bool = True


@dataclass
class Spec:
    path: Path
    id: str
    title: str
    status: str
    scenes: list[Scene]
    bgm: Bgm | None = None
    voice: Voice | None = None
    target_lufs: float = TARGET_LUFS
    credits: list[str] = field(default_factory=list)

    @property
    def dir(self) -> Path:
        return self.path.parent

    @property
    def duration(self) -> float:
        return round(sum(s.duration for s in self.scenes), 3)

    def scene_starts(self) -> list[float]:
        starts, t = [], 0.0
        for s in self.scenes:
            starts.append(round(t, 3))
            t += s.duration
        return starts

    def resolve(self, rel: str) -> Path:
        """Resolve a media path: absolute, relative to the short, or to the repo root."""
        p = Path(rel).expanduser()
        if p.is_absolute():
            return p
        local = self.dir / p
        return local if local.exists() else ROOT / p

    @property
    def lock_path(self) -> Path:
        return self.dir / "assets.lock.json"

    def load_lock(self) -> dict[str, Any]:
        if self.lock_path.exists():
            return json.loads(self.lock_path.read_text(encoding="utf-8"))
        return {"scenes": {}}

    def footage_path(self, scene: Scene) -> Path | None:
        """The file a scene will use: explicit `file`, else what `fetch` downloaded."""
        if scene.footage.file:
            return self.resolve(scene.footage.file)
        entry = self.load_lock().get("scenes", {}).get(str(scene.index))
        if entry and entry.get("query") == scene.footage.query:
            return self.resolve(entry["file"])
        return None


def _num(d: dict, key: str, default, errors: list[str], where: str, minimum=None):
    val = d.get(key, default)
    if val is None:
        return default
    try:
        val = float(val)
    except (TypeError, ValueError):
        errors.append(f"{where}: `{key}` must be a number, got {val!r}")
        return default
    if minimum is not None and val < minimum:
        errors.append(f"{where}: `{key}` must be >= {minimum}, got {val}")
    return val


def _choice(d: dict, key: str, default: str, allowed: set[str], errors: list[str], where: str) -> str:
    val = d.get(key, default)
    if val not in allowed:
        errors.append(f"{where}: `{key}` must be one of {sorted(allowed)}, got {val!r}")
        return default
    return val


def parse(data: dict[str, Any], path: Path) -> Spec:
    errors: list[str] = []
    if not isinstance(data, dict):
        raise SpecError(f"{path}: spec must be a YAML mapping")

    sid = str(data.get("id") or "").strip()
    if not sid:
        errors.append("`id` is required (e.g. MT-0001)")
    title = str(data.get("title") or "").strip()
    status = data.get("status", "SCRIPT_DRAFT")
    if status not in STATUSES:
        errors.append(f"`status` must be one of {STATUSES}, got {status!r}")

    scenes: list[Scene] = []
    raw_scenes = data.get("scenes") or []
    if not isinstance(raw_scenes, list) or not raw_scenes:
        errors.append("`scenes` must be a non-empty list")
        raw_scenes = []

    for i, rs in enumerate(raw_scenes):
        where = f"scenes[{i}]"
        if not isinstance(rs, dict):
            errors.append(f"{where}: must be a mapping")
            continue
        dur = _num(rs, "duration", 0.0, errors, where)
        if dur <= 0:
            errors.append(f"{where}: `duration` must be > 0 seconds")
            dur = 1.0

        rf = rs.get("footage") or {}
        if isinstance(rf, str):
            rf = {"file": rf}
        footage = Footage(
            file=rf.get("file"),
            query=rf.get("query"),
            provider=_choice(rf, "provider", "pexels", PROVIDERS, errors, f"{where}.footage"),
            pick=int(_num(rf, "pick", 0, errors, f"{where}.footage", minimum=0)),
            start=_num(rf, "start", 0.0, errors, f"{where}.footage", minimum=0),
        )
        if not footage.file and not footage.query:
            errors.append(f"{where}.footage: give a `file` or a stock `query`")

        texts: list[TextItem] = []
        for j, rt in enumerate(rs.get("text") or []):
            tw = f"{where}.text[{j}]"
            if isinstance(rt, str):
                rt = {"content": rt}
            content = str(rt.get("content") or "").strip()
            if not content:
                errors.append(f"{tw}: `content` is empty")
            start = _num(rt, "start", 0.0, errors, tw, minimum=0)
            end = _num(rt, "end", dur, errors, tw)
            if end <= start:
                errors.append(f"{tw}: `end` ({end}) must be after `start` ({start})")
            if end > dur + 1e-6:
                errors.append(f"{tw}: `end` ({end}) is past the scene duration ({dur})")
            hl = rt.get("highlight") or []
            if isinstance(hl, str):
                hl = [hl]
            texts.append(TextItem(
                content=content, start=start, end=min(end, dur),
                style=_choice(rt, "style", "caption", TEXT_STYLES, errors, tw),
                animation=_choice(rt, "animation", "pop", ANIMATIONS, errors, tw),
                position=_choice(rt, "position", "center", POSITIONS, errors, tw),
                highlight=[str(h) for h in hl],
                highlight_color=_choice(rt, "highlight_color", "cyan", HIGHLIGHT_COLORS, errors, tw),
            ))

        sfx: list[Sfx] = []
        for j, rx in enumerate(rs.get("sfx") or []):
            xw = f"{where}.sfx[{j}]"
            if isinstance(rx, str):
                rx = {"file": rx}
            if not rx.get("file"):
                errors.append(f"{xw}: `file` is required")
                continue
            at = _num(rx, "at", 0.0, errors, xw, minimum=0)
            if at > dur:
                errors.append(f"{xw}: `at` ({at}) is past the scene duration ({dur})")
            sfx.append(Sfx(file=rx["file"], at=at, volume_db=_num(rx, "volume_db", 0.0, errors, xw)))

        scenes.append(Scene(
            index=i, duration=dur, footage=footage,
            motion=_choice(rs, "motion", "none", MOTIONS, errors, where),
            transition=_choice(rs, "transition", "cut", TRANSITIONS, errors, where),
            grade=bool(rs.get("grade", True)),
            text=texts, sfx=sfx, note=str(rs.get("note") or ""),
        ))

    audio = data.get("audio") or {}
    bgm = voice = None
    rb = audio.get("bgm")
    if isinstance(rb, str):
        rb = {"file": rb}
    if rb:
        if not rb.get("file"):
            errors.append("audio.bgm: `file` is required")
        else:
            bgm = Bgm(
                file=rb["file"],
                volume_db=_num(rb, "volume_db", -16.0, errors, "audio.bgm"),
                offset=_num(rb, "offset", 0.0, errors, "audio.bgm", minimum=0),
                fade_in=_num(rb, "fade_in", 0.3, errors, "audio.bgm", minimum=0),
                fade_out=_num(rb, "fade_out", 1.5, errors, "audio.bgm", minimum=0),
            )
    rv = audio.get("voice")
    if isinstance(rv, str):
        rv = {"file": rv}
    if rv and rv.get("file"):
        voice = Voice(
            file=rv["file"],
            volume_db=_num(rv, "volume_db", 0.0, errors, "audio.voice"),
            duck_bgm=bool(rv.get("duck_bgm", True)),
        )

    if errors:
        raise SpecError(f"{path}:\n  - " + "\n  - ".join(errors))

    return Spec(
        path=path, id=sid, title=title, status=status, scenes=scenes, bgm=bgm, voice=voice,
        target_lufs=float(audio.get("target_lufs", TARGET_LUFS)),
        credits=[str(c) for c in (data.get("credits") or [])],
    )


def load(path: str | Path) -> Spec:
    """Load a spec from a spec.yaml file or a short's folder."""
    p = Path(path)
    if p.is_dir():
        p = p / "spec.yaml"
    if not p.exists():
        raise SpecError(f"spec not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return parse(data, p.resolve())


def missing_media(spec: Spec) -> list[str]:
    """Media files the spec references that are not on disk (footage needing fetch included)."""
    missing = []
    for s in spec.scenes:
        fp = spec.footage_path(s)
        if fp is None:
            missing.append(f"scene {s.index}: footage query {s.footage.query!r} not fetched yet")
        elif not fp.exists():
            missing.append(f"scene {s.index}: footage {fp}")
        for x in s.sfx:
            if not spec.resolve(x.file).exists():
                missing.append(f"scene {s.index}: sfx {x.file}")
    if spec.bgm and not spec.resolve(spec.bgm.file).exists():
        missing.append(f"bgm {spec.bgm.file}")
    if spec.voice and not spec.resolve(spec.voice.file).exists():
        missing.append(f"voice {spec.voice.file}")
    return missing
