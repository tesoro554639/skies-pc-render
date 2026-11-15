# Generalized encode: python encode_film.py [film-folder]  e.g. python encode_film.py films/knocker-upper
# Reads total_frames + output name from film-folder/film.json.
import subprocess, sys, json, pathlib
film = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("films/knocker-upper")
info = json.loads((film/"film.json").read_text())
total = int(info["total_frames"]); out = info["output"]
subprocess.run([sys.executable, "tools/render/encode.py", str(film/"final_v1"), str(total),
    str(film/"audio/mix.wav"), str(film/"caps"), str(film/out)], check=True)
print(f"ENCODED {film/out}", flush=True)
