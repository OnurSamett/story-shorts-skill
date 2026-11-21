# STORY BIBLE: "<series title>"

This file is the single source of truth. Every part, shot and image prompt must obey it.
Write it BEFORE any outline, script or image.

## 1. Map of locations
Draw the whole place as a simple ASCII map (floors, rooms, corridors, stairs, exits) and list the ONLY legal routes
between places. Every move between places must be one of these routes and must be shown on screen.

```
FLOOR 3  [Stairs A]---- corridor ----[Room 3B]
FLOOR 2  [Stairs A]---- corridor ----[Library]---[Service stairs]
FLOOR 1  [Stairs A (blocked)]--[Room 104]--corridor--[Storage room]--[Cafeteria]--[Kitchen]--[Service stairs]
```
- Blocked / unusable places and why:
- Route the hero takes: A -> B -> C -> ...
- For each location give a short FIXED look (walls, floor, furniture, windows) reused in every prompt:
  - `<loc id>`: ...

## 2. One timeline, one light per part
One continuous timeline. No day/night or location jumps unless shown on screen (e.g. a labeled flashback).
| Part | Time | Light (state it in every prompt) |
|---|---|---|
| 1 | 10:42-10:55 | bright daylight; red emergency lamps after the alarm |
| 2 | | |

## 3. Cast with fixed descriptions
One line per character, copied verbatim into `"cast"` in scenes.json (the name in an image prompt is replaced by it).
- NAME (age, hair, eyes, clothes, one unique accessory, build)
- Never change outfits. Say what must NOT be there (e.g. "no glasses").

## 4. Rules for every part
- Starts exactly where the previous part ended; first sentence is a one-line "previously".
- 1-2 locations per part; show how the hero gets from one place to the next.
- 60-90 seconds, 12-16 scenes, ends on a cliffhanger.
- Camera: mostly medium and wide shots; at most 2 extreme close-ups per part, only at emotional peaks.
- A/B choice card only from later parts (new accounts: not in the first parts); pick the winner yourself until comments arrive.
- Words to avoid in narration (TTS content filter): bite, blood, kill, ...

## 5. Part outlines
### PART 1 - "<title>" (<location>, <time>)
1. Hook: ...
2. ...
12. Cliffhanger: ...

### PART 2 - "<title>"
1. Previously: ...
