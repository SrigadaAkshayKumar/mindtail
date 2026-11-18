---
name: clip-video
description: Turn any long video (YouTube link or local file) into ready-to-post vertical short-form clips for YouTube Shorts, Instagram Reels and TikTok. It downloads and transcribes the video, picks the best self-contained moments, cuts and face-reframes them to 9:16, and optionally adds a simple clean edit (smooth zooms, word-by-word captions in the creator's brand colours, 1-2 subtle whooshes). Use whenever the user pastes a YouTube/video link or video file and wants clips, shorts, reels, TikToks, highlights or "the best moments", even if they only say "clip this", "cut this up" or "make shorts from this".
---

# Clip Video

Turns one long video into several vertical shorts. **You (Claude) are the editor who picks the
moments**; the scripts in this repo do the download, transcription, cutting and rendering.
Everything runs locally and free: no API keys and no uploads.

All commands run from the repo root with `python run.py ...` (it uses the repo's own `.venv`).
On Windows use `python`; on macOS/Linux use `python3` if `python` isn't found.

## 0. Setup (first time only)
If `.venv/` doesn't exist, run `python install.py`. If it reports a missing ffmpeg/Node, show
the user the exact install command it printed, and ask them to run it and restart the terminal.
Install Remotion (`python install.py --remotion`) only if the user asks for the Remotion engine.

## 1. Get the transcript
```
python run.py fetch "<youtube url or path to a video file>"
```
- This downloads the **audio only** (fast) and transcribes it with word timestamps (Whisper,
  on the CPU). It takes about 1/4 to 1/2 of the video's length. Run it in the background for
  long videos and tell the user roughly how long it will take.
- It prints the project name and the transcript path: `output/<project>/transcript/transcript.txt`.
- If YouTube blocks the download ("confirm you're not a bot"), retry with
  `--cookies-from-browser chrome` (or firefox / edge). Ask the user which browser they use.
- Non-English videos are detected automatically.

## 2. Pick the moments (your job)
Read `references/picking-moments.md` first, then read the **whole** `transcript.txt`.
Choose the best 3–8 self-contained clips (hook → story → payoff, 25–60 s ideal), and write
`output/<project>/clips.json` in the format given there. Prefer continuous ranges; splice only
when it clearly makes a better short.

**Get exact times.** A transcript line can hold several sentences. When your hook or payoff
starts or ends **inside** a line, look up the exact word time instead of using the line's time:
```
python run.py find <project> "the thing that separates"     -> start 457.35 ...
python run.py find <project> "never give it to you"         -> ... end 474.95
```
Use the `start` of the hook's first words and the `end` of the payoff's last words. Otherwise a
clip can open with leftover words from the previous sentence.

Before moving on, show the user a short table: #, title, length, hook line, score.
Don't wait for approval unless they asked to review picks first. Keep going.

## 3. Cut to vertical
First check the boundaries (it takes a second and cuts nothing):
```
python run.py cut <project> --check
```
It warns when a clip starts or ends mid-sentence, or falls outside 15–90 s. For every warning,
look at the quoted words. Fix the range with `run.py find` unless the cut is clearly intentional
(e.g. a splice point, or a start right after "but"). Then cut:
```
python run.py cut <project>
```
This downloads the video (max 1080p) the first time, snaps every range to whole words, reframes
each camera shot around the speaker's face (9:16, 1080x1920), and writes `clips/NN-title.mp4`.
Shots with no detectable face (slides, b-roll) get a blurred-background "fit" layout.
Use `--horizontal` to keep 16:9, and `--clips 2,4` to redo only some.

**These raw cuts are already postable.** If the user only wanted clips, stop here and report.

## 4. Brand colours for captions (quick, don't overthink)
The captions use white text, a black outline, and **one accent colour** for the spoken word and
the emphasis words. Choose the accent like this:
1. **If you know the creator's signature caption or brand colour** (from your knowledge, or a
   quick web search if you have that tool), set it:
   `python run.py brand <project> --accent "#RRGGBB" --note "creator brand colour"`.
   Only do this when you're confident; don't guess.
2. Otherwise do nothing: the edit step picks the strongest non-skin colour from the video itself
   (graphics, set lighting, clothing) and brightens it for readability, or falls back to a
   classic short-form yellow.
3. Sanity-check the printed colour. It must read clearly over the footage and not clash. If it
   looks off (e.g. muddy brown or near-grey), override it with a clean colour from the printed
   palette or with `#FFD60A`.

## 5. Simple edit (optional, recommended)
```
python run.py edit <project>
```
For each clip this adds:
- **Zooms**: it opens on a quick zoom-out, then alternates wide and punched-in framing about
  every 3–5 s on sentence ends, with one or two smooth emphasis zooms and a slow push in between.
  It always scales around the face. Camera cuts and splices get a framing change, which hides
  the jump.
- **Captions**: 1–3 words at a time, bold, popping in word by word. The spoken word lights up in
  the accent colour, and the `emphasis` words from clips.json stay highlighted. An `.srt` is also
  written.
- **Sound**: at most 2 subtle whooshes: one on the opening zoom and one on an emphasis zoom. The voice is lightly compressed, and the
  whole mix is normalised to -14 LUFS.

Options: `--sfx light|none`, `--no-zoom`, `--no-captions`, `--no-upper` (sentence case),
`--caption-y 1270` (higher number = lower on screen), `--size 96`, `--engine remotion`.
Read `references/editing.md` if the user wants a different look.

## 6. Deliver
Report the results as a short table: clip, length, file path. Point to
`output/<project>/edited/` (or `clips/` if not edited) and include each clip's posting caption
from clips.json. Mention that the files are ready to upload to Shorts, Reels and TikTok.

## Rules
- Never invent words. Clips only contain what the speaker actually said.
- Never commit anything in `output/` (it's gitignored). Don't upload anything anywhere.
- Remind users to clip only videos they own or have permission to use.
- If a step fails, read the error. The scripts print the fix (missing tool, cookies, etc.).
