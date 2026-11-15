# Generalized render loop: python run_loop.py [film-folder]  e.g. python run_loop.py films/knocker-upper
# Reads total_frames from film-folder/film.json. Already-rendered frames are skipped, so stopping and re-running is safe.
import subprocess, sys, os, glob, time, json, pathlib, shutil
film = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("films/knocker-upper")
info = json.loads((film/"film.json").read_text())
total = int(info["total_frames"])
print(f"Film: {info.get('title', info['name'])} - {total} frames total", flush=True)
while True:
    procs = str(os.cpu_count() or 4)
    subprocess.run([sys.executable, "tools/render/render.py",
        "--web", str(film/"engine/web"), "--out", str(film/"final_v1"),
        "--range", f"0-{total-1}", "--w", "540", "--procs", procs,
        "--ms", "1", "--sm", "2048"])
    # IMPORTANT: preserve worker frames before the next run wipes _w*
    out = film/"final_v1"
    for d in sorted(out.glob("_w*")):
        if not d.is_dir():
            continue
        for f in sorted(d.glob("f_*.png")):
            shutil.move(str(f), str(out/f.name))
    done = len(glob.glob(str(out/"f_*.png")))
    print(f"frames done: {done}/{total}", flush=True)
    if done >= total:
        print("ALL FRAMES DONE - run encode now", flush=True)
        break
    time.sleep(5)
