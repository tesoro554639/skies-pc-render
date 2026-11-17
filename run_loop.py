# Generalized resumable render loop: python run_loop.py [film-folder] [--procs 4] [--mode gpu|cpu] [--encode]
# Reads total_frames from film.json. Already-rendered frames are skipped, so stopping and re-running is safe.
import argparse, subprocess, sys, os, time, json, pathlib, shutil

def rescue_worker_frames(out_dir: pathlib.Path) -> int:
    if not out_dir.is_dir():
        return 0
    moved = 0
    for d in sorted(out_dir.glob("_w*")):
        if not d.is_dir():
            continue
        for f in sorted(d.glob("f_*.png")):
            target = out_dir / f.name
            if not target.exists():
                try:
                    shutil.move(str(f), str(target))
                    moved += 1
                except OSError:
                    pass
    return moved

def count_done_frames(out_dir: pathlib.Path, total: int) -> int:
    if not out_dir.is_dir():
        return 0
    done = 0
    for f in out_dir.glob("f_*.png"):
        stem = f.stem
        if len(stem) == 7 and stem[2:].isdigit():
            idx = int(stem[2:])
            if 0 <= idx < total:
                done += 1
    return done

def main():
    ap = argparse.ArgumentParser(description="Multi-pass resilient Skies render loop.")
    ap.add_argument("film", nargs="?", default="films/knocker-upper", help="Path to film folder (default: films/knocker-upper)")
    ap.add_argument("--procs", type=int, help="Number of browser workers (default: safe auto 4 for GPU, 2 for CPU)")
    ap.add_argument("--mode", choices=["gpu", "cpu"], default="gpu", help="Render device mode (default: gpu)")
    ap.add_argument("--w", type=int, default=540, help="Render width (default: 540)")
    ap.add_argument("--ms", type=int, default=1, help="MSAA samples (default: 1)")
    ap.add_argument("--sm", type=int, default=2048, help="Shadow map resolution (default: 2048)")
    ap.add_argument("--range", help="Custom frame range, e.g. 0-1128 or 200-300")
    ap.add_argument("--encode", action="store_true", help="Automatically encode MP4 when all frames finish")
    ap.add_argument("--nvenc", action="store_true", help="Use NVENC when --encode is specified")
    args = ap.parse_args()

    film = pathlib.Path(args.film).resolve()
    json_path = film / "film.json"
    if not json_path.is_file():
        sys.exit(f"Error: film.json not found in {film}")

    info = json.loads(json_path.read_text(encoding="utf-8"))
    total = int(info["total_frames"])
    out_dir = film / "final_v1"
    web_dir = film / "engine" / "web"
    frame_range = args.range or f"0-{total - 1}"

    # Default procs: avoid crashing ANGLE GPU with too many Chromium instances
    if args.procs:
        procs = max(1, args.procs)
    else:
        cores = os.cpu_count() or 4
        procs = min(4, cores) if args.mode == "gpu" else min(cores, 8)

    print(f"Film: {info.get('title', film.name)} - {total} frames total", flush=True)
    print(f"Mode: {args.mode.upper()} | Workers: {procs} | Resolution: {args.w}x{round(args.w*16/9)} | Range: {frame_range}", flush=True)

    attempt = 1
    try:
        while True:
            cmd = [
                sys.executable, "-u", "tools/render/render.py",
                "--web", str(web_dir),
                "--out", str(out_dir),
                "--range", frame_range,
                "--w", str(args.w),
                "--procs", str(procs),
                "--ms", str(args.ms),
                "--sm", str(args.sm),
                "--mode", args.mode,
            ]
            subprocess.run(cmd)

            # Preserve worker frames immediately
            rescue_worker_frames(out_dir)
            done = count_done_frames(out_dir, total)
            print(f"Frames done: {done}/{total} ({done / total * 100:.1f}%)", flush=True)

            if done >= total:
                print("\nALL FRAMES DONE!", flush=True)
                if args.encode:
                    print("Starting automatic MP4 encoding...", flush=True)
                    encode_cmd = [sys.executable, "encode_film.py", str(film)]
                    if args.nvenc:
                        encode_cmd.append("--nvenc")
                    subprocess.run(encode_cmd, check=True)
                else:
                    print(f"Run 'python encode_film.py {film.name}' to encode the MP4.", flush=True)
                break

            attempt += 1
            print(f"Resuming remaining frames in pass {attempt}...", flush=True)
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nRender loop paused by user.", flush=True)
    finally:
        rescue_worker_frames(out_dir)

if __name__ == "__main__":
    main()
