# library/

Local media used by the Shorts. **Everything here except this file is git-ignored**:
media is large, and licensed files should not be redistributed through the repo.

```text
library/
├── footage/   downloaded by `python -m mindtail fetch` (provenance in each short's assets.lock.json)
├── music/     background tracks you download yourself
├── sfx/       whooshes, impacts, risers, pops
└── _samples/  synthetic test media from `python -m mindtail samples` (not for uploads)
```

For music and SFX, use only sources whose licence allows use in YouTube videos
(for example YouTube Audio Library or Pixabay). Read the licence on the
download page, and add a line to the Short's `credits:` with the track name,
author, source and licence. Name files so you can find them, e.g.
`music/dark-pulse-92bpm-pixabay-12345.mp3`.
