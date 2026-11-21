#!/usr/bin/env python3
"""Narration via fal.ai ElevenLabs v3 with word timestamps (about $0.10 per 1000 characters).

  python3 voice.py run <folder> [--voice Brian] [scene numbers...]
      -> <folder>/v{n}.m4a + kelime_zamanlari.json (word timings) + satir_zamanlari.json (line start times)
  python3 voice.py test "<sentence>" Brian Daniel ...
      -> voice_test/<voice>.mp3 samples

Each scene is read from "lines": [{"who": "NARRATOR", "t": "...", "show": k}] if present, otherwise from
"narration". By default every line is read by the narrator voice. Optional per-character voices in scenes.json:
  "voices": {"NINA": {"voice": "Jessica", "pitch": 1.18}}
Scene numbers (1-based) limit which scenes are regenerated.

Env: FAL_KEY (required, never written to disk or printed), ELEVEN_VOICE (default narrator voice),
     ELEVEN_STABILITY (default 0.4), FAL_TTS_URL (override the endpoint).
"""
import argparse, json, os, re, subprocess, sys, time, urllib.error, urllib.request

URL = os.environ.get("FAL_TTS_URL", "https://fal.run/fal-ai/elevenlabs/tts/eleven-v3")
GAP = 0.25  # silence between lines (seconds)
RISKY = re.compile(r"\b(bite|bites|bitten|bit|blood|bloody|kill|kills|killed|murder|gore|suicide)\b", re.I)


def tts(text, voice, out_mp3, stability):
    key = os.environ.get("FAL_KEY") or sys.exit("FAL_KEY is not set (export FAL_KEY=...)")
    body = json.dumps({"text": text, "voice": voice, "stability": stability, "timestamps": True}).encode()
    for k in range(4):  # retry on network trouble
        try:
            req = urllib.request.Request(URL, data=body, headers={"Authorization": f"Key {key}",
                                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                res = json.load(r)
            with urllib.request.urlopen(res["audio"]["url"], timeout=180) as r:
                open(out_mp3, "wb").write(r.read())
            return res.get("timestamps") or []
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:  # rejected (often the content filter): retrying will not help
                sys.exit(f"fal rejected the request ({e.code}): {e.read().decode()[:400]}\nTEXT: {text}\n"
                         "Hint: rephrase violent words (e.g. 'bites' -> 'hurt').")
            print("  server error, retrying:", e)
            time.sleep(4 * (k + 1))
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            print("  network error, retrying:", e)
            time.sleep(4 * (k + 1))
    sys.exit("network error: giving up")


def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", p]).decode().strip())


def to_wav(mp3, wav, pitch):
    af = "aresample=44100"
    if pitch != 1.0:  # raise pitch, keep tempo (child voices)
        af = f"asetrate=44100*{pitch},aresample=44100,atempo={1 / pitch:.4f}"
    af += ",afade=t=in:d=0.015"  # no click at line start
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-af", af, "-ac", "1", wav], check=True)


def run(a):
    data = json.load(open(os.path.join(a.folder, "scenes.json")))
    scenes = data["scenes"] if isinstance(data, dict) else data
    cast = {k: (v["voice"], float(v.get("pitch", 1.0))) for k, v in
            (data.get("voices", {}) if isinstance(data, dict) else {}).items()}
    only = {int(n) for n in a.scenes}
    wpath, opath = os.path.join(a.folder, "kelime_zamanlari.json"), os.path.join(a.folder, "satir_zamanlari.json")
    words = json.load(open(wpath)) if os.path.exists(wpath) else {}
    offs = json.load(open(opath)) if os.path.exists(opath) else {}
    tmp = os.path.join(a.folder, "_voice_tmp")
    os.makedirs(tmp, exist_ok=True)
    for i, sc in enumerate(scenes, 1):
        if only and i not in only:
            continue
        lines = sc.get("lines") or [{"who": "NARRATOR", "t": sc["narration"]}]
        wavs, segs, starts, t0 = [], [], [], 0.0
        for j, ln in enumerate(lines):
            if RISKY.search(ln["t"]):
                print(f"  warning: scene {i} line {j + 1} has a word the TTS content filter may reject: {ln['t'][:60]}")
            voice, pitch = cast.get(ln["who"], (a.voice, 1.0))
            mp3, wav = os.path.join(tmp, f"{i}_{j}.mp3"), os.path.join(tmp, f"{i}_{j}.wav")
            ts = tts(ln["t"], voice, mp3, a.stability)
            to_wav(mp3, wav, pitch)
            for s in ts:  # shift timestamps to the line start
                segs.append({"characters": s["characters"] + [" "],
                             "character_start_times_seconds": [x + t0 for x in s["character_start_times_seconds"]] + [0],
                             "character_end_times_seconds": [x + t0 for x in s["character_end_times_seconds"]] + [0]})
            starts.append(round(t0, 3))
            wavs.append(wav)
            t0 += dur(wav) + GAP
        flt = "".join(f"[{k}]apad=pad_dur={GAP}[p{k}];" for k in range(len(wavs)))
        flt += "".join(f"[p{k}]" for k in range(len(wavs))) + f"concat=n={len(wavs)}:v=0:a=1"
        args = []
        for w in wavs:
            args += ["-i", w]
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args, "-filter_complex", flt,
                        "-ar", "44100", "-ac", "1", os.path.join(a.folder, f"v{i}.m4a")], check=True)
        words[str(i)], offs[str(i)] = segs, starts
        json.dump(words, open(wpath, "w"))  # save after every scene so progress survives a failure
        json.dump(offs, open(opath, "w"))
        print("scene", i, "done", f"({len(lines)} lines)")


def test(a):
    os.makedirs("voice_test", exist_ok=True)
    for v in a.voices:
        tts(a.text, v, f"voice_test/{v}.mp3", a.stability)
        print("written:", f"voice_test/{v}.mp3")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--stability", type=float, default=float(os.environ.get("ELEVEN_STABILITY", "0.4")))
    r = sub.add_parser("run", parents=[common], help="narrate every scene of <folder>/scenes.json")
    r.add_argument("folder")
    r.add_argument("scenes", nargs="*", help="1-based scene numbers to (re)generate")
    r.add_argument("--voice", default=os.environ.get("ELEVEN_VOICE", "Brian"), help="narrator voice")
    r.set_defaults(fn=run)
    t = sub.add_parser("test", parents=[common], help="render one sentence with several voices")
    t.add_argument("text")
    t.add_argument("voices", nargs="+")
    t.set_defaults(fn=test)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
