# MINDTAIL

Hindi/Hinglish YouTube Shorts for the MINDTAIL channel (@MIND_TAIL_99): the mind and human behaviour.

## Clipping long videos into Shorts (the working method)

When the user pastes a video link or file, or asks for clips, shorts, reels or highlights, **use the
`clip-video` skill** (`.claude/skills/clip-video/SKILL.md`) and follow it end to end without stopping for
confirmation. It comes from [Plextrang/Claude-Video-Clipper](https://github.com/Plextrang/Claude-Video-Clipper)
(MIT, `clipper/LICENSE`).

- Run everything through `python run.py <command>` from the repo root. Setup is `python install.py`.
- Results go to `output/<project>/` (gitignored). Never commit or upload videos.
- Long steps (transcription, rendering) run in the background, with a progress update to the user.
- **Rights first:** clip only videos MINDTAIL owns or has written permission to use (keep the proof), or
  footage whose licence allows reuse (e.g. CC BY with credit). Never streamer clips, trailers or other
  channels' videos without permission. If the source's rights are unclear, ask before clipping.
- MINDTAIL captions: yellow `#FFD700` accent (`python run.py brand <project> --accent "#FFD700"`).

## Older prototype

`mindtail/` (ffmpeg stock-footage renderer), `shorts/`, `templates/`, `tests/`: the first prototype. The
production faceless pipeline now runs in `SrigadaAkshayKumar/ai-news-editor`, branch `mindtail`.
