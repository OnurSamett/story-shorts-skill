---
name: story-shorts
description: Use when making faceless vertical (9:16) animated multi-part story videos, e.g. a zombie POV series, with Claude writing the story, Codex generating images, ElevenLabs narration and ffmpeg doing the montage. No paid video model is needed.
---

# story-shorts

Pipeline: story bible -> outline per part -> character sheets -> anchored location images -> narration -> montage -> frame QA -> caption.
Scripts live in `scripts/` (path below is relative to this skill folder), templates in `templates/`.
Work in a project folder per part, e.g. `series/part1/` containing `scenes.json`.

## 1. Story bible first
Copy `templates/story_bible_template.md` and fill it in before anything else:
- a map of locations with the only legal routes between them,
- ONE timeline with the lighting for each part (state day/night in every image prompt),
- a cast with fixed one-line descriptions (hair, clothes, one unique accessory).
Every later step must obey this file. Do not start outlining until the user approves the bible.

## 2. Part-by-part outline
- Each part starts exactly where the previous one ended (first line = short "previously").
- Explain every move between places; never jump location or time of day.
- 1-2 locations per part, 60-90 s (12-16 scenes), ends on a cliffhanger.
- Mostly medium/wide shots; at most 2 extreme close-ups per part.
- New accounts: no A/B poll in the first parts. Add an A/B choice card only from later parts and pick the winner yourself until comments arrive.

## 3. Character reference sheets (6 expressions)
Put one entry per character in `"refs"` of scenes.json: a full-body front view plus six head close-ups with clearly different expressions (e.g. smile, bored, confused, terrified, crying, determined). Generate them first and let the user approve them:
`python3 scripts/gen_images.py <folder>` generates refs first (they are the first jobs).
Engines: Codex (default, ~1 min/image) or `--engine gemini` (Antigravity CLI, a few min/image). If Codex reports a usage limit, switch the remaining files to Gemini, or split the list: one Codex run and one Gemini run on different files can run at the same time (never two Codex runs).
Put the fixed descriptions in `"cast"`: names in prompts are expanded to them automatically.

## 4. Anchor scenes (consistent rooms)
Give every image a location id: `"loc": "classroom"` (or one scene-level `"loc"`). For each location the FIRST generated frame becomes the anchor and is automatically passed as an extra reference to every later image of the same location, so layout, furniture and lighting stay the same. Use `"anchor": false` on an image that must not use/become an anchor (extreme close-ups, window views, a deliberately different angle of lighting). Make the first frame of each location a clean wide establishing shot, and check it before generating the rest. Check with `--dry-run` first: it prints each job with its resolved refs and anchors and calls nothing.

## 5. Shot list (2-3 images per narration line)
For every image prompt state explicitly:
- camera position (wide from the back of the room, medium from the front, over the shoulder...),
- location and light ("bright late-morning daylight, NOT night"),
- a specific facial emotion,
- hands simple or out of frame (hands are where image models fail).
Events seen from another place must be framed from the viewer's position, e.g. "seen from INSIDE the classroom through the window, window frame visible in the foreground". Do not draw an event as if the camera stood next to it when the hero is somewhere else.
Scene fields: see `templates/scenes_example.json` (`images`, `narration` or `lines`, `chat`, `widgets`, `fx`, `text`, `accent`, `focus`).

## 6. Narration
One narrator reads everything, including phone messages (the chat card appears on screen while the line is read; use `lines` with `"show": k` to reveal k messages). Avoid violent words such as "bites" or "blood": the TTS content filter rejects them (`voice.py` warns about a few). Rephrase ("hurt", "wound", "scratch").
`export FAL_KEY=...` then `python3 scripts/voice.py run <folder> [--voice Brian]`. Try voices with `python3 scripts/voice.py test "sentence" Brian Daniel`.

## 7. Montage
`python3 scripts/render.py <folder>` (Pillow needed; see README for a venv). Output: `<folder>/<foldername>.mp4`. Options: `--speed 1.12`, `--pill`, `--out`.
Features: 2 s camera shots, 3-word Impact captions with yellow active word, big keyword at the top, chat card, widgets (counter, bar, pulse, tag, options), fx alarm/flicker, vignette, click-free PCM audio.

## 8. Frame QA before delivering
Look at every image (contact sheet or one by one) and at 2-3 frames of the final video. Check: lighting matches the timeline, location matches the scene, no duplicate frames, no text/letter artifacts, characters match the sheets, hands, nothing sudden like day <-> night. Regenerate bad ones by name: `python3 scripts/gen_images.py <folder> k3_2.png`, then re-render. Never send a video you have not looked at.

## 9. Caption / post
Fill `templates/post_caption_template.md` per part: hook question, 2-3 concrete details, question to the reader, cliffhanger, follow call, 5-8 hashtags, cover text.

## Known pitfalls
- Parallel Codex runs mix up output files: always sequential; the script md5-dedupes and retries once.
- `codex exec -i X` swallows the prompt: pass images as `--image=path` (the script does).
- ElevenLabs timestamps come in segments that can split a word: `render.py` merges them.
- The DIN-style font lacks the "·" glyph: the pill widget draws the dot itself.
- Image models drift: repeating the location description and the light in every prompt is cheaper than regenerating.
- Do not generate in the same folder from two jobs at once.
- Generating images is slow (about 1 min each): run it in the background and tell the user.
