#!/usr/bin/env python3
"""Sequential image generation with Codex (default) or Gemini (--engine gemini, Antigravity CLI),
with character references and per-location ANCHOR frames.

Never run two Codex jobs in parallel: concurrent `codex exec` runs mix up their output files.
One Codex run and one Gemini run on DIFFERENT files at the same time is fine (e.g. when Codex hits its limit).

scenes.json (see templates/scenes_example.json):
  "cast":  {"ALEX": "ALEX (17-year-old boy, messy brown hair, orange hoodie)", ...}   optional, name -> fixed description
  "refs":  {"alex_ref.png": "<prompt>" | {"prompt": "...", "from": ["existing.png"]}}  generated first, no references
  "scenes": [{"loc": "classroom",                      optional scene-level default location id
              "setting": "...",                         optional text appended to every image prompt of the scene
              "images": [{"file": "k1_1.png", "prompt": "...", "refs": ["alex_ref.png"],
                          "loc": "classroom",           optional (overrides the scene-level loc)
                          "setting": "...",             optional per-image override of the scene setting
                          "anchor": false}]}]           optional: opt out of the anchor mechanism for this image

Anchor logic: for each location id the FIRST image generated (job order) becomes that location's anchor.
Every later image with the same loc automatically gets the anchor appended to its refs (after the character
refs), so the room, furniture and lighting stay consistent. "anchor": false = this image neither receives
nor becomes an anchor. If a previous run already produced the anchor file it is reused on resume.

Usage:
  python3 gen_images.py <folder | scenes.json> [file names...] [--style anime2|anime|pixar3d] [--model NAME] [--dry-run]
With no file names only missing images are generated; with names those are (re)generated.
Env: CODEX_IMAGE_MODEL (model), STORY_STYLE (style preset).
"""
import argparse, hashlib, json, os, subprocess, sys, tempfile

DEFAULT_MODEL = "gpt-6.1-terra"
TAIL = "vertical 9:16 composition, hands kept simple or out of frame, absolutely no text, letters or numbers"
STYLES = {
    "anime2": ("2D anime style illustration, clean thin line art, soft cel shading, realistic anime proportions "
               "(not chibi), attractive well-drawn faces with a clear specific emotion, detailed painted background, "
               "cinematic lighting, " + TAIL),
    "anime": ("2D anime-inspired cartoon animation still, bold clean outlines, soft cel shading, big expressive eyes, "
              "rounded proportions with a slightly big head, rich detailed painted background, cinematic lighting, "
              "a clear specific facial emotion, " + TAIL),
    "pixar3d": ("3D Pixar-style animated film still, soft cinematic lighting, rich detailed environment, "
                "expressive stylized faces with a clear specific emotion, " + TAIL),
}
CHAR_NOTE = ("The attached image(s) are character reference sheets: keep each character's face, hair, proportions "
             "and clothes exactly the same as in the reference. Do not copy the reference layout. ")
ANCHOR_NOTE = ("The LAST attached image is an anchor frame of the SAME location: keep the room layout, furniture, wall "
               "colors, windows and lighting identical to it. Do not copy its characters or composition. ")


def build_jobs(data, style):
    """Return a list of job dicts in generation order (refs first, then scenes)."""
    cast = data.get("cast", {}) if isinstance(data, dict) else {}
    refs = data.get("refs", {}) if isinstance(data, dict) else {}
    scenes = data["scenes"] if isinstance(data, dict) else data

    def expand(p):
        for k in sorted(cast, key=len, reverse=True):
            if k in p:
                p = p.replace(k, cast[k], 1)
        return p

    jobs = []
    for f, p in refs.items():  # a ref value is a plain prompt or {"prompt": ..., "from": [existing images]}
        txt = p if isinstance(p, str) else p["prompt"]
        jobs.append({"file": f, "prompt": f"{expand(txt)}. {style}", "refs": [] if isinstance(p, str) else list(p.get("from", [])),
                     "loc": None, "anchor": False})
    for sc in scenes:
        for im in sc.get("images", []):
            if not im.get("prompt"):  # a ready-made frame, nothing to generate
                continue
            st = im.get("setting", sc.get("setting"))  # an image may override the scene setting
            setting = f" Setting: {st}." if st else ""
            jobs.append({"file": im["file"], "prompt": f"{expand(im['prompt'])}.{setting} {style}",
                         "refs": list(im.get("refs", [])), "loc": im.get("loc") or sc.get("loc"),
                         "anchor": im.get("anchor", True) is not False})
    return jobs


def resolve_refs(job, anchors):
    """Character refs + (anchor of the job's loc, if any). Returns (refs, uses_anchor)."""
    refs = list(job["refs"])
    anchor = anchors.get(job["loc"]) if job["loc"] and job["anchor"] else None
    if anchor and anchor != job["file"] and anchor not in refs:
        refs.append(anchor)
        return refs, True
    return refs, False


def codex_generate(folder, model, out, prompt, ref_files, anchored):
    work = tempfile.mkdtemp(prefix="storygen_")
    args = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "workspace-write",
            "-m", model, "-c", 'model_reasoning_effort="medium"']
    note = ""
    n_char = len(ref_files) - (1 if anchored else 0)
    for r in ref_files:
        args.append(f"--image={os.path.abspath(os.path.join(folder, r))}")  # NOT '-i x': it swallows the prompt
    note = (CHAR_NOTE if n_char > 0 else "") + (ANCHOR_NOTE if anchored else "")
    args.append("Use your image generation tool to create ONE image and save it in the current directory as "
                f"image.png. {note}Image description: {prompt}. After saving, reply only with: image.png")
    for _ in range(2):
        try:
            subprocess.run(args, cwd=work, capture_output=True, text=True, timeout=420)
        except subprocess.TimeoutExpired:
            pass
        p = os.path.join(work, "image.png")
        if os.path.exists(p):
            os.replace(p, out)
            return True
    return False


def find_agy():
    for p in (os.environ.get("AGY_BIN"), "/Applications/Gemini.app/Contents/Helpers/agy",
              "/Applications/Antigravity.app/Contents/Helpers/agy"):
        if p and os.path.exists(p):
            return p
    import shutil
    return shutil.which("agy")


def gemini_generate(folder, model, out, prompt, ref_files, anchored):
    """Gemini via the Antigravity CLI (`agy`). Its agent can only make images through an image subagent, which
    keeps running after the CLI returns and saves into ~/.gemini/antigravity-cli/brain/<conversation>/ —
    so we read the conversation id from the stream and poll that folder. Shell commands are NOT allowed."""
    import glob, shutil, time
    agy = find_agy()
    if not agy:
        sys.exit("Antigravity CLI (agy) not found; install Gemini/Antigravity or set AGY_BIN")
    work = tempfile.mkdtemp(prefix="storygem_")
    names = []
    for r in ref_files:  # references are copied into the agent's working folder
        shutil.copy(os.path.join(folder, r), os.path.join(work, os.path.basename(r)))
        names.append(os.path.basename(r))
    n_char = len(ref_files) - (1 if anchored else 0)
    note = (CHAR_NOTE if n_char > 0 else "") + (ANCHOR_NOTE if anchored else "")
    if names:
        note += f"Reference files in the current directory: {', '.join(names)}. "
    task = (f"Create ONE image with the image-generator subagent (invoke_subagent) or generate_image. {note}"
            f"After invoking, wait until it has finished, then finish. Image description: {prompt}")
    allow = ["read_file", "view_file", "list_dir", "generate_image", "invoke_subagent", "manage_subagents",
             "wait", "wait_5_seconds", "finish"]
    for _ in range(2):
        try:
            p = subprocess.run([agy, "-p", task, "--model", model, "--mode", "accept-edits",
                                "--settings", json.dumps({"permissions": {"allow": allow}}),
                                "--output-format", "stream-json", "--print-timeout", "400s"],
                               cwd=work, capture_output=True, text=True, timeout=460)
            conv = json.loads(p.stdout.splitlines()[0]).get("conversation_id")
        except Exception:
            conv = None
        if not conv:
            continue
        brain = os.path.expanduser(f"~/.gemini/antigravity-cli/brain/{conv}")
        for _ in range(30):  # up to ~2.5 min after the CLI returns
            imgs = sorted(glob.glob(f"{brain}/*.png") + glob.glob(f"{brain}/*.jp*g"), key=os.path.getmtime)
            if imgs:
                time.sleep(2)  # let the write finish
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", imgs[-1], out], check=True)
                return True
            time.sleep(5)
    return False


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description="Sequential Codex image generation with references and location anchors.")
    ap.add_argument("folder", help="project folder containing scenes.json")
    ap.add_argument("files", nargs="*", help="only (re)generate these file names")
    ap.add_argument("--style", choices=sorted(STYLES), default=os.environ.get("STORY_STYLE", "anime2"))
    ap.add_argument("--engine", choices=["codex", "gemini"], default=os.environ.get("STORY_ENGINE", "codex"),
                    help="image engine: codex (default) or gemini (Antigravity CLI); a different engine can run "
                         "at the same time on different files, e.g. when one hits its usage limit")
    ap.add_argument("--model", default=None,
                    help="model id (codex default: $CODEX_IMAGE_MODEL or built-in; gemini default: $GEMINI_IMAGE_MODEL "
                         "or gemini-4-hydrogen-medium)")
    ap.add_argument("--dry-run", action="store_true", help="print the job list with resolved refs/anchors; no Codex call")
    a = ap.parse_args()
    if a.model is None:
        a.model = (os.environ.get("GEMINI_IMAGE_MODEL", "gemini-4-hydrogen-medium") if a.engine == "gemini"
                   else os.environ.get("CODEX_IMAGE_MODEL", DEFAULT_MODEL))
    generate = gemini_generate if a.engine == "gemini" else codex_generate
    if a.style not in STYLES:
        sys.exit(f"unknown style {a.style!r}; choose from {sorted(STYLES)}")
    if os.path.isfile(a.folder):  # a path to a scenes json file is accepted too
        a.folder = os.path.dirname(os.path.abspath(a.folder))
        spec = os.path.abspath(sys.argv[1])
    else:
        spec = os.path.join(a.folder, "scenes.json")
    data = json.load(open(spec))
    jobs = build_jobs(data, STYLES[a.style])
    only = set(a.files)
    anchors, n_gen, n_skip = {}, 0, 0
    for job in jobs:
        f = job["file"]
        out = os.path.join(a.folder, f)
        refs, anchored = resolve_refs(job, anchors)
        skip = (only and f not in only) or (not only and os.path.exists(out))
        if skip and not a.dry_run:
            if job["loc"] and job["anchor"] and job["loc"] not in anchors and os.path.exists(out):
                anchors[job["loc"]] = f  # already-made first frame of a location stays its anchor
            n_skip += 1
            continue
        becomes = bool(job["loc"] and job["anchor"] and job["loc"] not in anchors)
        if a.dry_run:
            tag = "ANCHOR for " + job["loc"] if becomes else ""
            print(f"{'skip ' if skip else 'gen  '}{f:14} loc={job['loc'] or '-':12} refs={refs} {tag}")
            print(f"       prompt: {job['prompt'][:110]}...")
            if becomes:
                anchors[job["loc"]] = f
            continue
        for _ in range(2):  # a duplicate of another file means Codex mixed outputs: retry once
            ok = generate(a.folder, a.model, out, job["prompt"], refs, anchored)
            dup = ok and any(md5(out) == md5(os.path.join(a.folder, g)) for g in os.listdir(a.folder)
                             if g.endswith(".png") and g != f)
            if ok and not dup:
                break
        print(f, "ok" if ok and not dup else ("DUPLICATE" if dup else "FAILED"), flush=True)
        if ok and not dup:
            n_gen += 1
            if becomes:
                anchors[job["loc"]] = f
    if a.dry_run:
        print(f"\n{len(jobs)} jobs; anchors: {anchors or 'none'}")
    else:
        print(f"done: {n_gen} generated, {n_skip} skipped")


if __name__ == "__main__":
    main()
