#!/usr/bin/env python3
"""Free montage with ffmpeg + Pillow (no video model).

Per scene: several images cut together with slow camera moves (about 2 s per shot), word-by-word Impact captions
(3 words, active word yellow), optional big keyword at the top, phone chat card, info widgets, fx and a vignette.
Audio is concatenated as PCM (no clicks between scenes) and sped up slightly.

Widgets (scene "widgets"): pill (location/time tag, off unless --pill), counter, bar, pulse, tag, options.
fx (scene "fx"): "alarm" (pulsing red light), "flicker" (flickering fluorescent).

Usage: python3 render.py <folder> [--speed 1.12] [--pill] [--out file.mp4]
Needs: <folder>/scenes.json, v{n}.m4a, kelime_zamanlari.json (from voice.py), the images.
Env: STORY_SPEED (default 1.12), FONT_IMPACT / FONT_DIN / FONT_SANS (override font files).
"""
import argparse, json, math, os, random, subprocess, sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow is not installed. Create a virtual environment and run this script with it:\n"
             "  python3 -m venv .venv && . .venv/bin/activate && pip install Pillow\n"
             "  python scripts/render.py <folder>")

W, H, FPS = 1080, 1920, 30
SHOT = 2.2
RED, YEL, WHITE, GREY = (235, 64, 52), (255, 210, 40), (255, 255, 255), (160, 165, 175)
CARD = (18, 22, 30, 225)
FONT_CANDIDATES = {
    "impact": ["/System/Library/Fonts/Supplemental/Impact.ttf", "C:/Windows/Fonts/impact.ttf",
               "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf", "/usr/share/fonts/truetype/anton/Anton-Regular.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "din": ["/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "sans": ["/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/arial.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}
ENV_FONT = {"impact": "FONT_IMPACT", "din": "FONT_DIN", "sans": "FONT_SANS"}
_fc, _paths = {}, {}


def font(role, size):
    k = (role, size)
    if k not in _fc:
        if role not in _paths:
            cands = ([os.environ[ENV_FONT[role]]] if os.environ.get(ENV_FONT[role]) else []) + FONT_CANDIDATES[role]
            _paths[role] = next((p for p in cands if os.path.exists(p)), None)
            if _paths[role] is None:
                print(f"warning: no {role} font found, using Pillow's default (set {ENV_FONT[role]}=/path/to/font.ttf)")
        try:
            _fc[k] = ImageFont.truetype(_paths[role], size) if _paths[role] else ImageFont.load_default(size=size)
        except TypeError:  # Pillow < 10.1
            _fc[k] = ImageFont.load_default()
    return _fc[k]


def run(*a):
    subprocess.run(list(a), check=True)


def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", p]).decode().strip())


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def words_of(segs, speed):
    """Flatten ElevenLabs segments into (word, start, end). Merges words split across segment boundaries
    and glues punctuation-only tokens to the previous word."""
    chars, st, en = [], [], []
    for s in segs:
        chars += s["characters"]; st += s["character_start_times_seconds"]; en += s["character_end_times_seconds"]
    out, cur, s0, e0 = [], "", None, None
    for idx, (c, a, b) in enumerate(zip(chars, st, en)):
        if c.isspace() and a == 0 and b == 0 and idx > 0:  # synthetic space added at a segment boundary
            nxt = st[idx + 1] if idx + 1 < len(st) else None
            if nxt is not None and e0 is not None and nxt - e0 < 0.15:
                continue  # the word continues in the next segment: keep it together
        if c.isspace():
            if cur:
                out.append((cur, s0, e0))
            cur, s0 = "", None
        else:
            if s0 is None:
                s0 = a
            cur += c; e0 = b
    if cur:
        out.append((cur, s0, e0))
    merged = []
    for w, a, b in out:
        if merged and not any(ch.isalnum() for ch in w):
            merged[-1] = (merged[-1][0] + w, merged[-1][1], b)
        else:
            merged.append((w, a, b))
    return [(w, a / speed, b / speed) for w, a, b in merged]


# ---------------- widgets ----------------
def w_pill(d, wd, t):
    # DIN-like fonts may lack the middle dot: draw the parts separately with a drawn dot in between
    parts = [p.strip() for p in wd["text"].split("·")]
    f = font("din", 40)
    gap = 44
    tw = sum(d.textlength(p, font=f) for p in parts) + gap * (len(parts) - 1)
    x0, y0 = (W - tw) / 2 - 60, 170
    d.rounded_rectangle((x0, y0, x0 + tw + 120, y0 + 74), 37, fill=CARD)
    dot = RED if wd.get("dot", "red") == "red" else YEL
    a = int(140 + 115 * (0.5 + 0.5 * math.sin(t * 6)))
    d.ellipse((x0 + 30, y0 + 28, x0 + 48, y0 + 46), fill=dot + (a,))
    x = x0 + 70
    for j, p in enumerate(parts):
        d.text((x, y0 + 37), p, font=f, fill=WHITE, anchor="lm")
        x += d.textlength(p, font=f)
        if j < len(parts) - 1:
            d.ellipse((x + gap / 2 - 4, y0 + 33, x + gap / 2 + 4, y0 + 41), fill=GREY)
            x += gap


def w_counter(d, wd, t, T):
    k = ease((t - 0.3) / max(T - 1.2, 0.5))
    v = round(wd["from"] + (wd["to"] - wd["from"]) * k)
    y = wd.get("y", 330)
    lab, num = wd["label"], f"{v:,}"
    fl, fn = font("din", 34), font("din", 120)
    w = max(d.textlength(num, font=fn), d.textlength(lab, font=fl)) + 120
    x0 = (W - w) / 2
    d.rounded_rectangle((x0, y, x0 + w, y + 210), 30, fill=CARD)
    d.text((W / 2, y + 45), lab, font=fl, fill=GREY, anchor="mm")
    d.text((W / 2, y + 135), num, font=fn, fill=RED if wd.get("color") == "red" else WHITE, anchor="mm")


def w_bar(d, wd, t, T):
    k = ease((t - 0.3) / max(T - 1.2, 0.5))
    v = wd["from"] + (wd["to"] - wd["from"]) * k
    y, x0, x1 = wd.get("y", 560), 140, W - 140
    d.rounded_rectangle((x0 - 30, y, x1 + 30, y + 150), 28, fill=CARD)
    d.text((x0, y + 45), wd["label"], font=font("din", 40), fill=WHITE, anchor="lm")
    col = (80, 200, 120) if v < 40 else (YEL if v < 70 else RED)
    d.text((x1, y + 45), f"{int(v)}%", font=font("din", 44), fill=col, anchor="rm")
    d.rounded_rectangle((x0, y + 90, x1, y + 118), 14, fill=(60, 64, 74, 255))
    d.rounded_rectangle((x0, y + 90, x0 + (x1 - x0) * v / 100, y + 118), 14, fill=col)


def w_pulse(d, wd, t, T):
    k = ease((t - 0.2) / max(T - 1.0, 0.5))
    bpm = wd["from"] + (wd["to"] - wd["from"]) * k
    y, x0, x1 = wd.get("y", 330), 140, W - 140
    d.rounded_rectangle((x0 - 30, y, x1 + 30, y + 230), 28, fill=CARD)
    d.text((x0, y + 45), wd["label"], font=font("din", 36), fill=GREY, anchor="lm")
    d.text((x1, y + 50), f"{int(bpm)}", font=font("din", 70), fill=RED, anchor="rm")
    base, pts = y + 150, []
    period = 60.0 / bpm
    for px in range(x0, x1, 4):
        tt = t - (x1 - px) / 300.0  # the line scrolls right to left
        ph = (tt % period) / period
        if 0.10 < ph < 0.14:
            dy = -60 * math.sin((ph - 0.10) / 0.04 * math.pi)
        elif 0.14 < ph < 0.18:
            dy = 25 * math.sin((ph - 0.14) / 0.04 * math.pi)
        else:
            dy = 0
        pts.append((px, base + dy))
    d.line(pts, fill=RED, width=5)


def w_tag(d, wd, t):
    if t < 0.5:
        return
    s = ease((t - 0.5) / 0.25)
    cx, cy = wd["x"] * W, wd["y"] * H
    r = 46 * s
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=RED, width=7)
    f = font("din", 46)
    tw = d.textlength(wd["text"], font=f)
    bx0, by0 = cx - tw / 2 - 30, cy - 160
    d.rounded_rectangle((bx0, by0, bx0 + tw + 60, by0 + 76), 18, fill=RED + (int(255 * s),))
    d.text((cx, by0 + 38), wd["text"], font=f, fill=WHITE, anchor="mm")
    d.line((cx, by0 + 76, cx, cy - r), fill=RED, width=5)


def w_options(d, wd, t):
    y = wd.get("y", 360)
    for j, (letter, txt) in enumerate((("A", wd["a"]), ("B", wd["b"]))):
        st = 0.4 + j * 0.6
        if t < st:
            continue
        s = ease((t - st) / 0.3)
        yy = y + j * 190 + (1 - s) * 40
        d.rounded_rectangle((110, yy, W - 110, yy + 160), 32, fill=CARD)
        d.ellipse((150, yy + 30, 250, yy + 130), fill=(YEL if letter == "A" else RED))
        d.text((200, yy + 80), letter, font=font("din", 64), fill=(20, 20, 20), anchor="mm")
        d.text((290, yy + 80), txt, font=font("din", 58), fill=WHITE, anchor="lm")


def chat_card(d, msgs, k, title, me):
    """Dark phone chat card: header, sender names, big bubbles. Card height is fixed for all messages; messages
    appear one by one. Messages from `me` are blue and right-aligned."""
    f, fn = font("sans", 54), font("sans", 38)
    pad, maxw, gap, top = 34, 640, 26, 330
    boxes, y = [], 230
    for m in msgs:
        lines, cur = [], ""
        for w in m["msg"].split():
            tt = (cur + " " + w).strip()
            if d.textlength(tt, font=f) <= maxw:
                cur = tt
            else:
                lines.append(cur); cur = w
        lines.append(cur)
        bw = max(d.textlength(l, font=f) for l in lines) + pad * 2
        bh = len(lines) * 68 + pad * 2 - 10
        boxes.append((m, lines, bw, bh, y))
        y += bh + gap + 46
    total = y + 20
    d.rounded_rectangle((60, top, W - 60, top + total), 56, fill=(18, 18, 22, 238))
    d.rounded_rectangle((60, top, W - 60, top + 150), 56, fill=(40, 40, 48, 255))
    d.text((W / 2, top + 75), title, font=fn, fill=(235, 235, 235), anchor="mm")
    for m, lines, bw, bh, yy in boxes[:k]:
        mine = m["from"] in me
        x0 = (W - 100 - bw) if mine else 100
        yy += top
        d.text((x0 + (bw if mine else 0), yy - 40), m["from"], font=fn, fill=(150, 150, 160),
               anchor="rs" if mine else "ls")
        d.rounded_rectangle((x0, yy, x0 + bw, yy + bh), 44, fill=(10, 132, 255) if mine else (235, 235, 240))
        for li, l in enumerate(lines):
            d.text((x0 + pad, yy + pad - 6 + li * 68), l, font=f, fill=WHITE if mine else (20, 20, 24))


def subtitle(d, words, t):
    cur = None
    for wi, (w, a, b) in enumerate(words):
        nxt = words[wi + 1][1] if wi + 1 < len(words) else a + 10
        if a <= t < nxt:
            cur = wi
            break
    if cur is None:
        return
    g0 = (cur // 3) * 3  # 3-word groups
    chunk = [x[0].upper() for x in words[g0:g0 + 3]]
    size = 100
    while True:
        f = font("impact", size)
        sp = d.textlength(" ", font=f) + 18
        ws = [d.textlength(w, font=f) for w in chunk]
        if sum(ws) + sp * (len(chunk) - 1) <= W - 80 or size <= 60:
            break
        size -= 6
    x = (W - (sum(ws) + sp * (len(chunk) - 1))) / 2
    for i, w in enumerate(chunk):
        d.text((x, int(H * 0.80)), w, font=f, fill=YEL if g0 + i == cur else WHITE, anchor="lm",
               stroke_width=10, stroke_fill=(0, 0, 0))
        x += ws[i] + sp


def shot_clip(img, t, kind, focus, out):
    frames = max(int(t * FPS), 2)
    fx, fy = focus
    z0, z1, cx, cy = {"wide": (1.0, 1.08, 0.5, 0.5), "tight": (1.14, 1.22, fx, fy),
                      "drift": (1.1, 1.1, 0.42, fy)}[kind]
    cxe = f"({cx}+0.16*on/{frames})" if kind == "drift" else f"{cx}"
    zp = (f"zoompan=z='{z0}+({z1}-{z0})*on/{frames}':x='min(max({cxe}*iw-iw/zoom/2,0),iw-iw/zoom)'"
          f":y='min(max({cy}*ih-ih/zoom/2,0),ih-ih/zoom)':d={frames}:s={W}x{H}:fps={FPS}")
    run("ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img, "-vf",
        f"scale={int(W*1.5)}:{int(H*1.5)}:force_original_aspect_ratio=increase,crop={int(W*1.5)}:{int(H*1.5)},{zp}",
        "-t", f"{t:.3f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", out)


def main():
    ap = argparse.ArgumentParser(description="ffmpeg + Pillow montage for story shorts.")
    ap.add_argument("folder")
    ap.add_argument("--speed", type=float, default=float(os.environ.get("STORY_SPEED", os.environ.get("HIZ", "1.12"))),
                    help="narration speed-up (default 1.12)")
    ap.add_argument("--pill", action="store_true", help="draw the top location/time pill widgets (off by default)")
    ap.add_argument("--out", help="output mp4 (default <folder>/<folder name>.mp4)")
    a = ap.parse_args()
    folder, SPEED = os.path.abspath(a.folder), a.speed
    data = json.load(open(os.path.join(folder, "scenes.json")))
    scenes = data["scenes"] if isinstance(data, dict) else data
    times = json.load(open(os.path.join(folder, "kelime_zamanlari.json")))
    op = os.path.join(folder, "satir_zamanlari.json")
    offs = json.load(open(op)) if os.path.exists(op) else {}
    g = Image.radial_gradient("L").resize((W, H))
    vignette = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vignette.putalpha(g.point(lambda v: min(190, max(0, int((v - 120) * 1.6)))))
    tmp = os.path.join(folder, "_render_tmp")
    os.makedirs(tmp, exist_ok=True)
    clips, auds = [], []
    for i, sc in enumerate(scenes, 1):
        vo = os.path.join(tmp, f"fast{i}.wav")
        d0 = dur(os.path.join(folder, f"v{i}.m4a")) / SPEED
        T = d0 + 0.45
        if sc.get("chat"):
            T = max(T, 1.0 + 1.6 * len(sc["chat"]))
        run("ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(folder, f"v{i}.m4a"), "-af",
            f"atempo={SPEED},afade=t=in:d=0.02,apad=whole_dur={T:.3f}", "-t", f"{T:.3f}",
            "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", vo)  # PCM: no clicks when concatenating
        imgs = [im["file"] for im in sc["images"]] if sc.get("images") else [sc["image"]]
        k = max(len(imgs), round(T / SHOT))
        kinds = ["wide", "tight", "drift"]
        shots = []
        for j in range(k):
            c = os.path.join(tmp, f"sh{i}_{j}.mp4")
            shot_clip(os.path.join(folder, imgs[j % len(imgs)]), T / k, kinds[(j + i) % 3], sc.get("focus", [0.5, 0.55]), c)
            shots.append(c)
        lst = os.path.join(tmp, f"l{i}.txt")
        open(lst, "w").write("".join(f"file '{os.path.abspath(c)}'\n" for c in shots))
        base = os.path.join(tmp, f"base{i}.mp4")
        run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", base)
        words = words_of(times[str(i)], SPEED)
        chat = sc.get("chat", [])
        nchat = len(chat)
        senders = list(dict.fromkeys(m["from"] for m in chat))
        cm = sc.get("chat_me", data.get("chat_me") if isinstance(data, dict) else None)
        # "chat_me": sender name(s) shown as blue right-side bubbles; default: everyone except the first sender
        me = set(senders[1:]) if cm is None else ({cm} if isinstance(cm, str) else set(cm))
        title = sc.get("chat_title") or next((s for s in senders if s not in me), senders[0] if senders else "")
        out = os.path.join(tmp, f"scene{i}.mp4")
        p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-i", base, "-f", "rawvideo", "-pix_fmt", "rgba",
                              "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-filter_complex", "[0][1]overlay=0:0",
                              "-t", f"{T:.3f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", out],
                             stdin=subprocess.PIPE)
        fx = sc.get("fx", [])
        # chat bubbles appear when their line is read (satir_zamanlari.json), else evenly spaced
        lines, so = sc.get("lines", []), [x / SPEED for x in offs.get(str(i), [])]
        marks = [(so[j], ln["show"]) for j, ln in enumerate(lines) if "show" in ln and j < len(so)]
        rnd = random.Random(i)
        for fi in range(int(T * FPS) + 1):
            t = fi / FPS
            al = int(70 * (0.5 + 0.5 * math.sin(2 * math.pi * 1.3 * t))) if "alarm" in fx else 0
            img = Image.new("RGBA", (W, H), (255, 20, 20, al))
            if "flicker" in fx and rnd.random() < 0.12:
                img.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 110)))
            img.alpha_composite(vignette)
            d = ImageDraw.Draw(img)
            kw = sc.get("text") and 0.15 <= t < 1.5  # big keyword at scene start
            if kw:
                size = 170
                f = font("impact", size)
                while d.textlength(sc["text"], font=f) > W - 100 and size > 80:
                    size -= 8
                    f = font("impact", size)
                col = {"red": (255, 70, 60), "yellow": YEL}.get(sc.get("accent"), WHITE)
                d.text((W / 2, 340), sc["text"], font=f, fill=col, anchor="mm", stroke_width=14, stroke_fill=(0, 0, 0))
            for wd in sc.get("widgets", []):
                ty = wd["type"]
                if ty == "pill" and not (a.pill or os.environ.get("ETIKET")):
                    continue
                if kw and ty != "pill":  # widgets wait while the keyword is shown
                    continue
                if ty == "pill": w_pill(d, wd, t)
                elif ty == "counter": w_counter(d, wd, t, T)
                elif ty == "bar": w_bar(d, wd, t, T)
                elif ty == "pulse": w_pulse(d, wd, t, T)
                elif ty == "tag": w_tag(d, wd, t)
                elif ty == "options": w_options(d, wd, t)
            if nchat and marks:
                kk = max([kshow for s, kshow in marks if t >= s] or [0])
                if kk:
                    chat_card(d, chat, kk, title, me)
            elif nchat:
                kk = min(nchat, 1 + int(max(t - 0.4, 0) / ((T - 0.8) / nchat))) if t > 0.4 else 0
                if kk:
                    chat_card(d, chat, kk, title, me)
            subtitle(d, words, t)
            p.stdin.write(img.tobytes())
        p.stdin.close()
        p.wait()
        clips.append(out); auds.append(vo)
        print(f"scene {i}: {T:.1f}s")
    for name, items in (("list.txt", clips), ("alist.txt", auds)):
        open(os.path.join(tmp, name), "w").write("".join(f"file '{os.path.abspath(c)}'\n" for c in items))
    final = a.out or os.path.join(folder, f"{os.path.basename(folder)}.mp4")
    run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(tmp, "list.txt"),
        "-f", "concat", "-safe", "0", "-i", os.path.join(tmp, "alist.txt"),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", final)
    print("ready:", final, f"({dur(final):.1f}s)")


if __name__ == "__main__":
    main()
