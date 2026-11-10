# spec.yaml reference

One `spec.yaml` per Short describes the whole edit. Times are in seconds.
Paths are relative to the Short's folder or the repo root (e.g. `library/sfx/whoosh.wav`).
Run `python -m mindtail check <short>` after editing: it lists every mistake at once.

```yaml
id: MT-0001
title: "Working title"
status: SCRIPT_DRAFT        # see "Stages" below

audio:
  bgm:
    file: library/music/track.mp3
    volume_db: -10          # level before final loudness normalisation
    offset: 0               # start this many seconds into the track
    fade_in: 0.3
    fade_out: 1.5
  voice:                    # optional, added once the voiceover is decided
    file: voice/vo.wav
    volume_db: 0
    duck_bgm: true          # music dips automatically while the voice speaks
  target_lufs: -14          # final integrated loudness

scenes:
  - duration: 2.5
    footage:
      query: "crowded metro station"   # stock search (run `fetch`)
      provider: pexels                 # pexels | pixabay
      pick: 0                          # 0 = best match; raise it to try another clip
      start: 0                         # seconds into the clip
      # file: library/footage/my-clip.mp4   # OR a local file/image instead of query
    motion: zoom_in         # none | zoom_in | zoom_out (slow 10% push)
    transition: cut         # cut | flash (white flash) | fade (from black)
    grade: true             # MINDTAIL look: contrast, cool tint, vignette
    text:
      - content: "पहली line\nदूसरी line"   # \n = new line; English words switch font automatically
        style: hook          # hook (118px) | caption (86px) | small (58px) | tag (label box)
        animation: pop       # pop | punch | fade | slide_up | words (word-by-word) | none
        position: center     # upper | center | lower (all inside Shorts safe area)
        highlight: [line]    # words/phrases to colour
        highlight_color: cyan  # cyan (default) | yellow | red | white
        start: 0.1           # relative to the scene
        end: 2.4             # defaults to the scene end
    sfx:
      - file: library/sfx/whoosh.wav
        at: 0.0              # relative to the scene
        volume_db: -6
    note: "free-form note for the editor"

credits:
  - "Music: <track> by <artist> (<source + licence>)"
```

## Mixing guide

- Put a **whoosh/impact on hard cuts** and a **riser** into reveals; keep most
  sound effects at -6 to -12 dB so they support, not shout.
- With a voiceover, start background music around -12 dB and let `duck_bgm`
  handle the dips. Without voice, music can sit near -6 to -10 dB.
- The final mix is normalised to `target_lufs` (default -14 LUFS, true peak
  -1.5 dBTP), so relative levels are what matter.

## Stages

`IDEA → SELECTED → RESEARCHED → SCRIPT_DRAFT → SCRIPT_APPROVED → VOICE_READY →
VISUALS_READY → EDITED → QC_APPROVED → UPLOAD_READY → PUBLISHED → ANALYZED`

Only move a Short forward when the artifact and approval for that stage exist.

## Outputs

`render` writes into `shorts/<short>/render/`:

- `<ID>.mp4`: the video (H.264 1080×1920 30 fps, AAC 48 kHz)
- `<ID>.render.json`: what went into it
- `<ID>.qc.json`: automatic check results

`fetch` writes `assets.lock.json` (source page, author, licence for each
clip). Commit that file; it is your footage provenance record.
