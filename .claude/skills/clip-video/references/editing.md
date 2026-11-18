# The simple edit: how it works and how to change it

The edit is deliberately simple: clean zooms, readable captions, and a few quiet sound effects.
No flashy transitions, emojis or motion graphics.

## Where things live
| What | File | Knobs |
|---|---|---|
| Zoom rhythm and levels | `clipper/plan.py` (`WIDE`, `PUNCH`, `DRIFT`, `OPEN_SCALE`, `beat_bounds`) | punch levels, beat length (2.8 s min) |
| Caption grouping | `clipper/plan.py` `caption_groups` | `max_words=3`, `max_chars=16`, `max_dur=1.6` |
| Caption look (python engine) | `clipper/edit.py` `write_ass` | font, outline, pop timing |
| Caption look (remotion engine) | `remotion/src/Clip.tsx` | same, in React |
| Sound effects | `clipper/plan.py` `sfx_cues`, files in `assets/sfx/` | gains in dB, which moments get one |
| Brand colour | `clipper/brand.py` / `brand.json` in the project | `python run.py brand <project> --accent "#hex"` |

## Common requests
- **"Captions higher/lower"**: `--caption-y` (centre line in px out of 1920; 1270 by default,
  about two-thirds down; around 1500 sits lower, around 1100 near mid-chest).
- **"Bigger/smaller captions"**: `--size` (96 by default).
- **"Not all caps"**: `--no-upper`.
- **"No sound effects" / "only one"**: `--sfx none` / `--sfx light`.
- **"Less zooming"**: `--no-zoom` for none, or raise the 2.8 s minimum in `beat_bounds`.
- **"Use my own sounds"**: drop files into `assets/sfx/` with `whoosh`, `hit` or `click`
  in the file name. They're scanned automatically (files that hold several sounds are split at
  the silences).
- **"Different font"**: put the .ttf in `assets/fonts/`, then pass its family name and file name
  through the `opts` in `edit.py` (`font`, `font_file`).

## Two engines, one plan
`plan.py` computes the camera for every frame, the caption timings and the sound cues.
- `--engine python` (default) draws it with OpenCV + ffmpeg/libass. It needs no extra installs
  and is fastest.
- `--engine remotion` draws the same plan with React/Remotion (`python install.py --remotion`).
  It has slightly smoother text rendering. It's free for individuals and small teams; companies
  should check Remotion's license.

The audio mix is the same in both engines.
