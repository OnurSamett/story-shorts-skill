# story-shorts

A Claude Code skill that turns an idea into faceless, vertical (1080x1920) animated multi-part story videos, for example a zombie POV series. Claude writes the story bible, outline and shot list; Codex generates the images; ElevenLabs (through fal.ai) narrates; ffmpeg + Pillow do the montage with camera moves, word-by-word captions, chat cards and info widgets. No paid video-generation model is used.

## Requirements
- Claude Code
- Codex CLI, logged in (image generation runs through `codex exec`)
- `ffmpeg` and `ffprobe` on PATH
- Python 3 with Pillow (for `render.py` only)
- A fal.ai key in the `FAL_KEY` environment variable (for `voice.py` only)

## Install as a Claude Code skill
```bash
cp -r story-shorts ~/.claude/skills/story-shorts   # folder name = skill name
```
Pillow in a virtual environment (if your system Python is locked down):
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install Pillow
```

## Quick start
```bash
mkdir -p series/part1 && cp templates/scenes_example.json series/part1/scenes.json
python3 scripts/gen_images.py series/part1 --dry-run   # job list with refs and anchors, calls nothing
python3 scripts/gen_images.py series/part1             # sequential, resumable (only missing files)
export FAL_KEY=...                                     # never commit this
python3 scripts/voice.py run series/part1 --voice Brian
python3 scripts/render.py series/part1                 # -> series/part1/part1.mp4
```
Image styles: `--style anime2` (default), `anime`, `pixar3d` (or env `STORY_STYLE`). Image model: `--model` or env `CODEX_IMAGE_MODEL`. Narrator voice: `--voice` or env `ELEVEN_VOICE`. Render speed: `--speed` or env `STORY_SPEED`. Fonts: env `FONT_IMPACT`, `FONT_DIN`, `FONT_SANS`.

## scenes.json
See `templates/scenes_example.json`. Top level: `cast`, `refs`, `chat_me`, optional `voices`, `scenes`. Scene: `narration` or `lines`, `images` (`file`, `prompt`, `refs`, `loc`, `anchor`, `setting`), `loc`, `setting`, `chat`, `widgets`, `fx`, `text`, `accent`, `focus`. Timing files keep their original names, `kelime_zamanlari.json` and `satir_zamanlari.json`.

## Costs
- Voice: about $0.10 per 1000 characters on fal.ai ElevenLabs v3 (a 75 s part is roughly 900-1200 characters).
- Images: generated through your ChatGPT plan via Codex; no per-image fee but it counts against plan limits.
- ffmpeg/Pillow: free.

## Limitations
- No true character animation: motion is camera pans/zooms and cuts between stills.
- Image generation is sequential, about 1 minute per image; a 14-scene part with 2-3 images per scene takes roughly 30-45 minutes.
- Consistency depends on reference sheets and anchors; always check frames before publishing.
- Narration uses one voice for everything.

## License
MIT, see [LICENSE](LICENSE).
