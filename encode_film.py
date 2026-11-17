# Generalized encode: python encode_film.py [film-folder] [--nvenc] [--crf 17] [--cq 18]
# Reads total_frames + output name from film-folder/film.json and encodes finished MP4.
import argparse, subprocess, sys, json, pathlib

def main():
    ap = argparse.ArgumentParser(description="Encode rendered frames into a high-quality 1080x1920 MP4.")
    ap.add_argument("film", nargs="?", default="films/knocker-upper", help="Path to film folder (default: films/knocker-upper)")
    ap.add_argument("--nvenc", action="store_true", help="Use NVIDIA NVENC hardware encoder")
    ap.add_argument("--crf", type=int, default=17, help="libx264 quality factor (default: 17)")
    ap.add_argument("--cq", type=int, default=18, help="NVENC quality factor (default: 18)")
    ap.add_argument("--out", help="Custom output MP4 path")
    args = ap.parse_args()

    film = pathlib.Path(args.film).resolve()
    json_path = film / "film.json"
    if not json_path.is_file():
        sys.exit(f"Error: film.json not found in {film}")

    info = json.loads(json_path.read_text(encoding="utf-8"))
    total = int(info["total_frames"])
    out_name = args.out or info.get("output", f"{film.name}_1080p.mp4")
    out_path = film / out_name if not pathlib.Path(out_name).is_absolute() else pathlib.Path(out_name)

    cmd = [
        sys.executable, "tools/render/encode.py",
        str(film / "final_v1"),
        str(total),
        str(film / "audio" / "mix.wav"),
        str(film / "caps"),
        str(out_path),
        "--crf", str(args.crf),
        "--cq", str(args.cq),
    ]
    if args.nvenc:
        cmd.append("--nvenc")

    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    main()
