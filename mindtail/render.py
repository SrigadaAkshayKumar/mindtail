"""Render a Short spec to a 1080x1920 MP4.

Steps
  1. Each scene's footage is cut, scaled/cropped to 9:16, optionally zoomed,
     colour graded and given an in-transition -> build/seg_XX.mp4
  2. Segments are joined -> build/video.mp4 (no audio)
  3. On-screen text -> build/captions.ass
  4. Background music + voice + timed sound effects are mixed -> build/mix.wav
     (music is ducked under the voice when there is one)
  5. The mix is measured and loudness-normalised (two-pass loudnorm), the
     captions are burned in, and the final file is encoded.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import ff
from .captions import write_ass
from .config import AUDIO_RATE, FONTS_DIR, FPS, HEIGHT, LRA, TRUE_PEAK, WIDTH
from .spec import IMAGE_EXTS, Scene, Spec, SpecError, missing_media

AFMT = f"aformat=sample_fmts=fltp:sample_rates={AUDIO_RATE}:channel_layouts=stereo"
GRADE = "eq=contrast=1.08:saturation=0.9:brightness=-0.02,colorbalance=bs=0.06:bm=0.03,vignette=angle=PI/5"
ZOOM = 0.10  # 10% zoom over the scene
PLACEHOLDER_COLOURS = [("0x000814", "0x00b4d8"), ("0x03045e", "0x00e5ff"),
                       ("0x10002b", "0x3a86ff"), ("0x000000", "0x90e0ef")]


def _log(msg: str) -> None:
    print(msg, flush=True)


def _segment(spec: Spec, scene: Scene, out: Path, placeholder: bool, preview: bool, verbose: bool) -> list[str]:
    """Render one scene's video. Returns warnings."""
    warnings: list[str] = []
    d = scene.duration
    src = spec.footage_path(scene)
    inputs: list[str]
    if src is not None and src.exists():
        if src.suffix.lower() in IMAGE_EXTS:
            inputs = ["-loop", "1", "-framerate", str(FPS), "-t", f"{d + 0.5}", "-i", str(src)]
        else:
            avail = ff.duration(src) - scene.footage.start
            if avail < d - 0.05:
                warnings.append(f"scene {scene.index}: clip has only {avail:.2f}s after start, "
                                f"needs {d:.2f}s; the last frame is held")
            inputs = ["-ss", f"{scene.footage.start}", "-i", str(src)]
    elif placeholder:
        c0, c1 = PLACEHOLDER_COLOURS[scene.index % len(PLACEHOLDER_COLOURS)]
        label = re.sub(r"[^A-Za-z0-9 ]", "", scene.footage.query or Path(scene.footage.file or "").stem)[:28]
        font = ff.filter_path(FONTS_DIR / "NotoSans-Bold.ttf")
        inputs = ["-f", "lavfi", "-i",
                  f"gradients=s={WIDTH}x{HEIGHT}:r={FPS}:d={d + 0.5}:c0={c0}:c1={c1}:speed=0.03,"
                  f"drawtext=fontfile={font}:text='PLACEHOLDER {scene.index + 1}  {label}':"
                  f"fontcolor=white@0.55:fontsize=40:x=(w-tw)/2:y=h-260"]
        warnings.append(f"scene {scene.index}: using a placeholder (no footage on disk)")
    else:
        raise SpecError(f"scene {scene.index}: footage missing; run `fetch` or add the file")

    frames = max(1, round(d * FPS))
    vf = [f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos",
          f"crop={WIDTH}:{HEIGHT}", "setsar=1", f"fps={FPS}",
          f"tpad=stop_mode=clone:stop_duration={d}"]
    if scene.motion in ("zoom_in", "zoom_out"):
        z = f"1+{ZOOM}*on/{frames}" if scene.motion == "zoom_in" else f"{1 + ZOOM}-{ZOOM}*on/{frames}"
        # upscale first so the per-frame crop moves in half-pixel steps (less jitter)
        vf += [f"scale={WIDTH * 2}:{HEIGHT * 2}:flags=lanczos",
               f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={WIDTH}x{HEIGHT}:fps={FPS}"]
    if scene.grade:
        vf.append(GRADE)
    if scene.transition == "flash":
        vf.append("fade=t=in:st=0:d=0.15:color=white")
    elif scene.transition == "fade":
        vf.append("fade=t=in:st=0:d=0.3")
    vf.append("format=yuv420p")

    ff.run([*inputs, "-t", f"{d}", "-vf", ",".join(vf), "-an",
            "-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast",
            "-crf", "20" if preview else "14", "-r", str(FPS), str(out)], verbose=verbose)
    return warnings


def _mix(spec: Spec, out: Path, placeholder: bool, verbose: bool) -> list[str]:
    """Mix music, voice and sound effects into a float WAV of the video's length."""
    warnings: list[str] = []
    D = spec.duration
    inputs = ["-f", "lavfi", "-t", f"{D}", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo"]
    chains, mix_labels = [f"[0:a]{AFMT}[base]"], ["[base]"]
    n = 1

    def available(rel: str, what: str) -> Path | None:
        p = spec.resolve(rel)
        if p.exists():
            return p
        if placeholder:
            warnings.append(f"{what} missing, left out: {rel}")
            return None
        raise SpecError(f"{what} missing: {rel}")

    bgm_label = None
    if spec.bgm and (p := available(spec.bgm.file, "bgm")):
        b = spec.bgm
        inputs += ["-stream_loop", "-1", "-ss", f"{b.offset}", "-i", str(p)]
        fo = min(b.fade_out, D / 2)
        chains.append(f"[{n}:a]{AFMT},atrim=0:{D},asetpts=PTS-STARTPTS,volume={b.volume_db}dB,"
                      f"afade=t=in:st=0:d={b.fade_in},afade=t=out:st={max(0.0, D - fo):.3f}:d={fo}[bgm]")
        bgm_label = "[bgm]"
        n += 1

    if spec.voice and (p := available(spec.voice.file, "voice")):
        v = spec.voice
        inputs += ["-i", str(p)]
        chains.append(f"[{n}:a]{AFMT},volume={v.volume_db}dB,apad,atrim=0:{D}[voice]")
        n += 1
        if v.duck_bgm and bgm_label:
            chains.append("[voice]asplit=2[vmix][vsc]")
            chains.append(f"{bgm_label}[vsc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[bgmd]")
            bgm_label = "[bgmd]"
            mix_labels.append("[vmix]")
        else:
            mix_labels.append("[voice]")
    if bgm_label:
        mix_labels.insert(1, bgm_label)

    for scene, start in zip(spec.scenes, spec.scene_starts()):
        for x in scene.sfx:
            p = available(x.file, f"scene {scene.index} sfx")
            if not p:
                continue
            ms = int(round((start + x.at) * 1000))
            inputs += ["-i", str(p)]
            chains.append(f"[{n}:a]{AFMT},volume={x.volume_db}dB,adelay={ms}:all=1[s{n}]")
            mix_labels.append(f"[s{n}]")
            n += 1

    chains.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:"
                  f"normalize=0:dropout_transition=0[out]")
    ff.run([*inputs, "-filter_complex", ";".join(chains), "-map", "[out]",
            "-t", f"{D}", "-c:a", "pcm_f32le", "-ar", str(AUDIO_RATE), str(out)], verbose=verbose)
    return warnings


def _loudnorm_filter(mix: Path, target: float) -> str | None:
    stderr = ff.run(["-i", str(mix), "-af", f"loudnorm=I={target}:TP={TRUE_PEAK}:LRA={LRA}:print_format=json",
                     "-f", "null", "-"])
    m = ff.parse_loudnorm(stderr)
    if m.get("input_i") in ("-inf", "inf") or float(m["input_i"]) < -70:
        return None  # silent mix: nothing to normalise
    return (f"loudnorm=I={target}:TP={TRUE_PEAK}:LRA={LRA}:measured_I={m['input_i']}:"
            f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
            f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,"
            f"aresample={AUDIO_RATE}")


def render(spec: Spec, out: Path | None = None, placeholder: bool = False,
           preview: bool = False, verbose: bool = False) -> tuple[Path, list[str]]:
    ff.require()
    if not placeholder:
        missing = missing_media(spec)
        if missing:
            raise SpecError("missing media (run `fetch`, add the files, or use --placeholder):\n  - "
                            + "\n  - ".join(missing))

    build = spec.dir / "build"
    build.mkdir(exist_ok=True)
    out = out or spec.dir / "render" / f"{spec.id}{'-preview' if preview else ''}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    segs = []
    for scene in spec.scenes:
        seg = build / f"seg_{scene.index:02d}.mp4"
        _log(f"[{spec.id}] scene {scene.index + 1}/{len(spec.scenes)} ({scene.duration:.2f}s)")
        warnings += _segment(spec, scene, seg, placeholder, preview, verbose)
        segs.append(seg)

    concat_list = build / "segments.txt"
    concat_list.write_text("".join(f"file '{s.name}'\n" for s in segs), encoding="utf-8")
    video = build / "video.mp4"
    ff.run(["-f", "concat", "-safe", "0", "-i", concat_list.name, "-c", "copy", video.name],
           cwd=build, verbose=verbose)

    ass = write_ass(spec, build / "captions.ass")

    _log(f"[{spec.id}] mixing audio")
    mix = build / "mix.wav"
    warnings += _mix(spec, mix, placeholder, verbose)
    norm = _loudnorm_filter(mix, spec.target_lufs)
    if norm is None:
        warnings.append("audio mix is silent (no music, voice or sound effects)")

    _log(f"[{spec.id}] encoding final video")
    vf = f"ass={ff.filter_path(ass)}:fontsdir={ff.filter_path(FONTS_DIR)}"
    args = ["-i", str(video), "-i", str(mix), "-map", "0:v", "-map", "1:a", "-vf", vf]
    if norm:
        args += ["-af", norm]
    args += ["-c:v", "libx264", "-preset", "veryfast" if preview else "medium",
             "-crf", "23" if preview else "18", "-profile:v", "high", "-pix_fmt", "yuv420p",
             "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_RATE), "-ac", "2",
             "-t", f"{spec.duration}", "-movflags", "+faststart", str(out)]
    ff.run(args, verbose=verbose)

    manifest = {
        "id": spec.id, "title": spec.title, "output": str(out.name),
        "rendered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration": spec.duration, "preview": preview, "placeholder": placeholder,
        "scenes": [{"index": s.index, "duration": s.duration,
                    "footage": str(spec.footage_path(s) or "placeholder")} for s in spec.scenes],
        "bgm": spec.bgm.file if spec.bgm else None,
        "voice": spec.voice.file if spec.voice else None,
        "warnings": warnings,
    }
    out.with_suffix(".render.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                               encoding="utf-8")
    return out, warnings
