"""Generate original placeholder media for testing the pipeline.

Everything here is synthesised by ffmpeg (no third-party footage or audio),
so it is safe to use for tests and demos. It is NOT meant for real uploads.
"""
from __future__ import annotations

from pathlib import Path

from . import ff
from .config import LIBRARY_DIR

SAMPLES = LIBRARY_DIR / "_samples"

FOOTAGE = {
    # landscape on purpose, to exercise the 9:16 crop
    "neural-landscape.mp4": "mandelbrot=s=1280x720:r=30:end_scale=0.05,hue=h=190:s=1.4",
    "cells-portrait.mp4": "life=s=540x960:r=30:mold=10:ratio=0.12:life_color=#00e5ff:death_color=#001018,scale=1080:1920:flags=neighbor",
    "waves-portrait.mp4": "gradients=s=1080x1920:r=30:c0=0x000814:c1=0x00b4d8:c2=0x03045e:n=3:speed=0.05",
    "grid-landscape.mp4": "testsrc2=s=1920x1080:r=30,hue=s=0.3,eq=brightness=-0.15",
}

AUDIO = {
    # 92 BPM pulse with a dark pad (original, synthesised)
    "music/pulse-92bpm.wav": (
        "aevalsrc='0.55*sin(2*PI*(45+90*exp(-25*mod(t,0.652)))*mod(t,0.652))*exp(-7*mod(t,0.652))"
        "+0.06*sin(2*PI*110*t)*(0.6+0.4*sin(2*PI*0.25*t))+0.04*sin(2*PI*164.81*t)"
        "+0.03*sin(2*PI*220.5*t)|0.55*sin(2*PI*(45+90*exp(-25*mod(t,0.652)))*mod(t,0.652))*exp(-7*mod(t,0.652))"
        "+0.06*sin(2*PI*110.4*t)*(0.6+0.4*sin(2*PI*0.25*t))+0.04*sin(2*PI*164.5*t)+0.03*sin(2*PI*220*t)'"
        ":s=48000:d=40", "lowpass=f=5000"),
    "sfx/whoosh.wav": ("anoisesrc=d=0.6:c=pink:a=0.6:r=48000",
                       "highpass=f=400,lowpass=f=6000,afade=t=in:d=0.35:curve=exp,afade=t=out:st=0.35:d=0.25"),
    "sfx/impact.wav": ("aevalsrc='0.9*sin(2*PI*(38+120*exp(-18*t))*t)*exp(-4.5*t)':s=48000:d=1.4",
                       "alimiter=limit=0.9"),
    "sfx/riser.wav": ("aevalsrc='0.25*sin(2*PI*(200+900*t*t/4)*t)*(t/2)':s=48000:d=2",
                      "afade=t=out:st=1.85:d=0.15"),
    "sfx/pop.wav": ("aevalsrc='0.6*sin(2*PI*880*t)*exp(-14*t)+0.3*sin(2*PI*1320*t)*exp(-20*t)':s=48000:d=0.4",
                    "anull"),
}


def generate(force: bool = False) -> list[Path]:
    ff.require()
    made = []
    for name, src in FOOTAGE.items():
        out = SAMPLES / "footage" / name
        if out.exists() and not force:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        ff.run(["-f", "lavfi", "-i", src, "-t", "6", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "20", "-pix_fmt", "yuv420p", str(out)])
        made.append(out)
    for name, (src, af) in AUDIO.items():
        out = SAMPLES / name
        if out.exists() and not force:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        ff.run(["-f", "lavfi", "-i", src, "-af", af, "-ac", "2", "-ar", "48000", str(out)])
        made.append(out)
    return made
