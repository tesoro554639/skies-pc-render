"""Local web-app backend + native Chrome app window launcher for Skies Render."""

from __future__ import annotations

import argparse
import ctypes
import http.server
import io
import json
import os
import pathlib
import platform
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import wave
import webbrowser
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
TOOLS_RENDER = ROOT / "tools" / "render"
GUI_HTML = ROOT / "tools" / "gui" / "index.html"
FILMS_DIR = ROOT / "films"

CHROME_PATHS = [
    pathlib.Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    pathlib.Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    pathlib.Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    pathlib.Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


HISTORY_FILE = TOOLS_RENDER / "history.json"


def open_path_native(target: pathlib.Path) -> None:
    """Cross-platform helper to open a file or folder in the default system viewer."""
    try:
        if os.name == "nt":
            os.startfile(str(target))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as exc:
        print(f"Error opening {target}: {exc}", flush=True)


def reveal_path_native(target: pathlib.Path) -> None:
    """Reveal a file or folder in the platform's native file explorer."""
    try:
        if os.name == "nt":
            if target.is_file():
                subprocess.Popen(["explorer.exe", f"/select,{target}"])
            else:
                subprocess.Popen(["explorer.exe", str(target)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target.parent if target.is_file() else target)])
    except Exception as exc:
        print(f"Error revealing {target}: {exc}", flush=True)


def discover_all_mp4s(extra_films: list[pathlib.Path] | None = None) -> list[dict]:
    """Scan and return rich metadata for all generated MP4 files across all films."""
    films = discover_films(extra_films)
    videos: list[dict] = []
    seen_paths: set[pathlib.Path] = set()

    for film_dir in films:
        info = read_film_info(film_dir)
        for mp4 in sorted(film_dir.glob("*.mp4")):
            rp = mp4.resolve()
            if rp in seen_paths or not mp4.is_file() or mp4.stat().st_size == 0:
                continue
            seen_paths.add(rp)
            stat = mp4.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 1)
            mtime = stat.st_mtime
            mtime_str = time.strftime("%b %d, %Y %I:%M %p", time.localtime(mtime))
            total_frames = info["total_frames"]
            duration = round(total_frames / 30.0, 2) if total_frames else 0.0

            # Scan available frames for a good poster frame
            out_dir = film_dir / "final_v1"
            poster_frame = 200
            if (out_dir / "f_00200.png").is_file():
                poster_frame = 200
            elif (out_dir / "f_00000.png").is_file():
                poster_frame = 0

            videos.append({
                "id": str(rp),
                "filmId": str(film_dir),
                "filmName": film_dir.name,
                "filmTitle": info["title"],
                "filename": mp4.name,
                "filePath": str(rp),
                "sizeMb": size_mb,
                "sizeBytes": stat.st_size,
                "mtime": int(mtime * 1000),
                "mtimeFormatted": mtime_str,
                "durationSeconds": duration,
                "totalFrames": total_frames,
                "isPrimary": mp4.name == info["output"],
                "posterUrl": f"/api/preview?film={urllib.parse.quote(str(film_dir))}&frame={poster_frame}&source=final",
                "videoUrl": f"/api/video?path={urllib.parse.quote(str(rp))}",
            })

    videos.sort(key=lambda v: v["mtime"], reverse=True)
    return videos


def get_history(extra_films: list[pathlib.Path] | None = None) -> list[dict]:
    """Load persistent encode history or populate from existing MP4 files."""
    if HISTORY_FILE.is_file():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    history: list[dict] = []
    for v in discover_all_mp4s(extra_films):
        history.append({
            "id": f"init_{v['filename']}",
            "filmName": v["filmName"],
            "filmTitle": v["filmTitle"],
            "filename": v["filename"],
            "filePath": v["filePath"],
            "encoder": "libx264",
            "totalFrames": v["totalFrames"],
            "duration": f"{v['durationSeconds']:.1f}s",
            "sizeMb": f"{v['sizeMb']} MB",
            "timestamp": v["mtime"],
            "date": v["mtimeFormatted"],
            "status": "Completed",
        })
    return history


def record_encode_history(entry: dict) -> None:
    """Save a new encode run entry into history.json."""
    history = get_history()
    history.insert(0, entry)
    if len(history) > 100:
        history = history[:100]
    try:
        HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"Error saving history: {exc}", flush=True)


def discover_films(extra_paths: list[pathlib.Path] | None = None) -> list[pathlib.Path]:
    """Return sorted film folders containing film.json and engine/web."""
    found: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    candidates: list[pathlib.Path] = []
    if FILMS_DIR.is_dir():
        candidates.extend(sorted(p for p in FILMS_DIR.iterdir() if p.is_dir()))
    if extra_paths:
        candidates.extend(extra_paths)
    for p in candidates:
        rp = p.resolve()
        if rp not in seen and (rp / "film.json").is_file() and (rp / "engine" / "web").is_dir():
            seen.add(rp)
            found.append(rp)
    return found


def read_film_info(film_dir: pathlib.Path) -> dict:
    """Load film.json metadata with safe fallbacks."""
    json_path = film_dir / "film.json"
    if not json_path.is_file():
        return {
            "name": film_dir.name,
            "title": film_dir.name,
            "total_frames": 0,
            "output": f"{film_dir.name}_1080p.mp4",
        }
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return {
        "name": data.get("name", film_dir.name),
        "title": data.get("title", film_dir.name),
        "total_frames": int(data.get("total_frames", 0)),
        "output": data.get("output", f"{film_dir.name}_1080p.mp4"),
    }


def rescue_worker_frames(out_dir: pathlib.Path) -> int:
    """Move completed frame PNGs from all _w* folders into out_dir."""
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


def compact_ranges(indices: list[int], max_ranges: int = 8) -> list[str]:
    """Convert [0, 1, 2, 5, 8, 9, 10] into readable ['#0-2', '#5', '#8-10']."""
    if not indices:
        return []
    ranges: list[str] = []
    start = indices[0]
    end = indices[0]
    for i in indices[1:]:
        if i == end + 1:
            end = i
        else:
            ranges.append(f"#{start}-{end}" if start != end else f"#{start}")
            start = end = i
            if len(ranges) >= max_ranges:
                ranges.append(f"... +{len(indices) - indices.index(i)} more")
                return ranges
    ranges.append(f"#{start}-{end}" if start != end else f"#{start}")
    return ranges


def scan_frames(out_dir: pathlib.Path, total: int) -> dict:
    """Scan frames in out_dir and worker subfolders. Returns summary dict."""
    if not out_dir.is_dir():
        return {
            "done": 0,
            "latestIdx": None,
            "latestPath": None,
            "frames": [],
            "missingCount": total,
            "missingSamples": list(range(min(total, 10))),
        }
    seen: dict[int, pathlib.Path] = {}
    for f in out_dir.glob("f_*.png"):
        stem = f.stem
        if len(stem) == 7 and stem[2:].isdigit():
            idx = int(stem[2:])
            if 0 <= idx < total:
                seen[idx] = f
    for d in out_dir.glob("_w*"):
        if not d.is_dir():
            continue
        for f in d.glob("f_*.png"):
            stem = f.stem
            if len(stem) == 7 and stem[2:].isdigit():
                idx = int(stem[2:])
                if 0 <= idx < total and idx not in seen:
                    seen[idx] = f

    done = len(seen)
    sorted_indices = sorted(seen.keys())
    latest_idx = sorted_indices[-1] if sorted_indices else None
    latest_path = seen[latest_idx] if latest_idx is not None else None

    missing = [i for i in range(total) if i not in seen] if total > 0 else []

    latest_mtime = int(latest_path.stat().st_mtime * 1000) if latest_path and latest_path.is_file() else 0

    return {
        "done": done,
        "latestIdx": latest_idx,
        "latestPath": str(latest_path) if latest_path else None,
        "latestMtime": latest_mtime,
        "frames": sorted_indices,
        "missingCount": len(missing),
        "missingSamples": missing[:15],
        "missingRanges": compact_ranges(missing),
    }


def scan_test_frames(test_dir: pathlib.Path) -> list[int]:
    """Return sorted list of test frame indices present in test_dir."""
    if not test_dir.is_dir():
        return []
    indices: list[int] = []
    for f in test_dir.glob("f_*.png"):
        stem = f.stem
        if len(stem) == 7 and stem[2:].isdigit():
            indices.append(int(stem[2:]))
    return sorted(indices)


def extract_film_zip(
    zip_source: pathlib.Path | str | bytes | io.BytesIO,
    target_root: pathlib.Path = FILMS_DIR,
) -> tuple[pathlib.Path, dict, dict]:
    """Safely extracts a Skies film zip archive into films/<slug>/ and validates assets."""
    target_root = target_root.resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    if isinstance(zip_source, (str, pathlib.Path)):
        p_src = pathlib.Path(zip_source).resolve()
        if not p_src.is_file():
            raise FileNotFoundError(f"Zip archive not found: {p_src}")
        zf = zipfile.ZipFile(p_src, "r")
        fallback_slug = p_src.stem
    elif isinstance(zip_source, bytes):
        zf = zipfile.ZipFile(io.BytesIO(zip_source), "r")
        fallback_slug = "imported-film"
    else:
        zf = zipfile.ZipFile(zip_source, "r")
        fallback_slug = "imported-film"

    with zf:
        nl = zf.namelist()
        fjs = [n for n in nl if n.replace("\\", "/").endswith("film.json")]
        if not fjs:
            raise ValueError("Archive is not a valid Skies film pack: missing film.json")

        # Select the shallowest film.json descriptor
        fj_name = sorted(fjs, key=lambda x: len(x.replace("\\", "/").split("/")))[0]
        try:
            meta = json.loads(zf.read(fj_name).decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Failed to parse film.json in archive: {exc}")

        raw_slug = meta.get("name") or fallback_slug
        slug = re.sub(r"[^a-zA-Z0-9_\-]", "-", raw_slug).strip("-") or "imported-film"

        prefix = fj_name[:-len("film.json")].replace("\\", "/")
        target_dir = (target_root / slug).resolve()
        if not target_dir.is_relative_to(target_root):
            raise ValueError("Target directory escapes films directory")

        target_dir.mkdir(parents=True, exist_ok=True)

        for member in zf.infolist():
            raw_name = member.filename.replace("\\", "/")
            # Path traversal / security check: reject root slashes, drive letters, .. segments
            if raw_name.startswith("/") or re.match(r"^[a-zA-Z]:", raw_name):
                continue
            parts = [p for p in raw_name.split("/") if p]
            if ".." in parts:
                continue

            if raw_name.startswith(prefix):
                rel = raw_name[len(prefix):]
            else:
                rel = raw_name
            rel = rel.lstrip("/")
            if not rel:
                continue

            dest = (target_dir / rel).resolve()
            if not dest.is_relative_to(target_dir):
                continue  # Security guard against traversal

            if member.is_dir() or raw_name.endswith("/"):
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    # Ensure final_v1 output directory exists
    (target_dir / "final_v1").mkdir(parents=True, exist_ok=True)

    validation = validate_film(target_dir)
    return target_dir, meta, validation


def validate_film(film_dir: pathlib.Path) -> dict:
    """Run comprehensive pre-flight health check on a film directory."""
    checks = []
    info = read_film_info(film_dir)
    total_frames = info["total_frames"]

    # 1. film.json
    json_ok = (film_dir / "film.json").is_file() and total_frames > 0
    checks.append({
        "name": "film.json",
        "status": "ok" if json_ok else "error",
        "detail": f"{total_frames} frames defined, title: '{info['title']}'" if json_ok else "Missing or invalid film.json"
    })

    # 2. engine/web
    web_dir = film_dir / "engine" / "web"
    web_index = web_dir / "index.html"
    web_app = web_dir / "app.js"
    web_ok = web_index.is_file() and web_app.is_file()
    checks.append({
        "name": "WebGL Scene",
        "status": "ok" if web_ok else "error",
        "detail": f"Built app.js present ({web_app.stat().st_size // 1024} KB)" if web_ok else "Missing index.html or app.js in engine/web/"
    })

    # 3. audio/mix.wav
    audio_path = film_dir / "audio" / "mix.wav"
    audio_ok = audio_path.is_file()
    audio_detail = "Missing audio/mix.wav (silent audio fallback will be used)"
    audio_duration = 0.0
    if audio_ok:
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio_path)]
            dur_str = subprocess.run(cmd, capture_output=True, text=True, timeout=4).stdout.strip()
            audio_duration = float(dur_str)
            target_dur = total_frames / 30.0
            diff = abs(audio_duration - target_dur)
            audio_detail = f"{audio_duration:.2f}s audio (target: {target_dur:.2f}s, diff: {diff:.2f}s)"
        except Exception:
            audio_detail = f"{audio_path.stat().st_size // 1024} KB audio file"
    checks.append({
        "name": "Audio Mix",
        "status": "ok" if audio_ok else "warning",
        "detail": audio_detail
    })

    # 4. captions
    caps_dir = film_dir / "caps"
    caps_list = caps_dir / "list.txt"
    caps_count = 0
    if caps_list.is_file():
        try:
            caps_count = sum(1 for line in caps_list.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip().startswith("file "))
        except Exception:
            pass
    caps_ok = caps_count > 0
    checks.append({
        "name": "Captions",
        "status": "ok" if caps_ok else "warning",
        "detail": f"{caps_count} caption frames in list.txt" if caps_ok else "No captions found (video will encode without captions)"
    })

    # 5. rendered frames
    scan = scan_frames(film_dir / "final_v1", total_frames)
    frame_status = "ok" if scan["done"] >= total_frames and total_frames > 0 else ("warning" if scan["done"] > 0 else "info")
    checks.append({
        "name": "Rendered Frames",
        "status": frame_status,
        "detail": f"{scan['done']}/{total_frames} frames ({scan['missingCount']} missing)"
    })

    return {
        "film": str(film_dir),
        "title": info["title"],
        "checks": checks,
        "scan": scan,
    }


def parse_frame_spec(spec: str, total: int) -> tuple[str | None, str | None]:
    """Parse '10-50' as --range or '12,45,60-65' as --list indices."""
    raw = (spec or "").strip()
    if not raw:
        return None, None
    if "," not in raw and re.fullmatch(r"\d+\s*-\s*\d+", raw):
        parts = [int(p.strip()) for p in raw.split("-")]
        lo, hi = min(parts[0], parts[1]), max(parts[0], parts[1])
        lo = max(0, min(max(0, total - 1), lo))
        hi = max(0, min(max(0, total - 1), hi))
        return f"{lo}-{hi}", None
    indices: set[int] = set()
    for token in raw.split(","):
        tok = token.strip()
        if not tok:
            continue
        if re.fullmatch(r"\d+\s*-\s*\d+", tok):
            a, b = [int(x.strip()) for x in tok.split("-")]
            for i in range(min(a, b), max(a, b) + 1):
                if 0 <= i < total:
                    indices.add(i)
        elif tok.isdigit():
            val = int(tok)
            if 0 <= val < total:
                indices.add(val)
    if not indices:
        raise ValueError(f"Invalid frame range or list: '{raw}'")
    return None, ",".join(str(i) for i in sorted(indices))


def resolve_caption_for_frame(film_dir: pathlib.Path, frame_idx: int) -> pathlib.Path | None:
    """Resolve the exact caption overlay PNG matching frame_idx from caps/list.txt."""
    caps_dir = film_dir / "caps"
    list_path = caps_dir / "list.txt"
    if not list_path.is_file():
        return None
    target_t = max(0.0, frame_idx / 30.0)
    cur_t = 0.0
    cur_file = None
    last_file = None
    try:
        lines = list_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None

    for line in lines:
        s = line.strip()
        if s.startswith("file "):
            val = s[5:].strip().strip("'\"")
            cur_file = val
            last_file = val
        elif s.startswith("duration ") and cur_file is not None:
            try:
                dur = float(s.split()[1])
            except Exception:
                dur = 0.033333
            if cur_t <= target_t < cur_t + dur:
                cand = caps_dir / cur_file
                return cand if cand.is_file() else None
            cur_t += dur
            cur_file = None

    if last_file:
        cand = caps_dir / last_file
        return cand if cand.is_file() else None
    return None


def compute_audio_waveform(wav_path: pathlib.Path, num_bars: int = 200) -> dict:
    """Compute normalized peak amplitude bars for PCM WAV (8/16/24/32-bit)."""
    if not wav_path.is_file():
        return {"bars": [], "duration": 0.0, "sampleRate": 0, "channels": 0}
    with wave.open(str(wav_path), "rb") as w:
        ch = w.getnchannels()
        sw = w.getsampwidth()
        fr = w.getframerate()
        nf = w.getnframes()
        dur = round(nf / fr, 2) if fr else 0.0
        if nf == 0 or sw not in (1, 2, 3, 4):
            return {"bars": [0.0] * num_bars, "duration": dur, "sampleRate": fr, "channels": ch}

        max_val = float((1 << (8 * sw - 1)) - 1) if sw > 1 else 128.0
        step_frames = max(1, nf // num_bars)
        sample_stride = max(1, step_frames // 48)
        frame_bytes = ch * sw
        bars: list[float] = []

        for b in range(num_bars):
            start_frame = int((b / num_bars) * nf)
            end_frame = min(nf, int(((b + 1) / num_bars) * nf))
            w.setpos(start_frame)
            chunk = w.readframes(max(1, end_frame - start_frame))
            peak = 0.0
            for f_off in range(0, len(chunk) - frame_bytes + 1, sample_stride * frame_bytes):
                s_bytes = chunk[f_off:f_off + sw]
                if sw == 1:
                    val = abs(s_bytes[0] - 128)
                elif sw == 2:
                    val = abs(struct.unpack("<h", s_bytes)[0])
                elif sw == 3:
                    val = abs(int.from_bytes(s_bytes, "little", signed=True))
                else:
                    val = abs(struct.unpack("<i", s_bytes)[0])
                if val > peak:
                    peak = float(val)
            bars.append(round(min(1.0, peak / max_val), 3))

        return {"bars": bars, "duration": dur, "sampleRate": fr, "channels": ch}


def compute_film_metrics(film_dir: pathlib.Path) -> dict:
    """Compute disk usage breakdown and flag tiny/corrupt rendered frame anomalies."""
    info = read_film_info(film_dir)
    total = info["total_frames"]
    out_dir = film_dir / "final_v1"
    sizes: dict[int, int] = {}

    if out_dir.is_dir():
        for f in out_dir.glob("f_*.png"):
            stem = f.stem
            if len(stem) == 7 and stem[2:].isdigit():
                sizes[int(stem[2:])] = f.stat().st_size

    worker_dirs = list(out_dir.glob("_w*")) if out_dir.is_dir() else []
    worker_bytes = sum(
        p.stat().st_size
        for d in worker_dirs if d.is_dir()
        for p in d.rglob("*") if p.is_file()
    )

    test_dir = film_dir / "test_gpu"
    test_bytes = sum(p.stat().st_size for p in test_dir.rglob("*") if p.is_file()) if test_dir.is_dir() else 0
    audio_file = film_dir / "audio" / "mix.wav"
    audio_bytes = audio_file.stat().st_size if audio_file.is_file() else 0
    caps_dir = film_dir / "caps"
    caps_bytes = sum(p.stat().st_size for p in caps_dir.rglob("*") if p.is_file()) if caps_dir.is_dir() else 0
    mp4_bytes = sum(p.stat().st_size for p in film_dir.glob("*.mp4") if p.is_file())

    size_vals = list(sizes.values())
    median_kb = round(statistics.median(size_vals) / 1024, 1) if size_vals else 0.0
    min_kb = round(min(size_vals) / 1024, 1) if size_vals else 0.0
    max_kb = round(max(size_vals) / 1024, 1) if size_vals else 0.0

    # Frames smaller than 4 KB or <20% of median typically indicate blank/crashed WebGL frames
    threshold = max(4096, int(median_kb * 1024 * 0.2)) if size_vals else 4096
    anomalies = sorted(idx for idx, sz in sizes.items() if sz < threshold)

    return {
        "totalFrames": total,
        "renderedCount": len(sizes),
        "framesMb": round(sum(size_vals) / (1024 * 1024), 1),
        "medianFrameKb": median_kb,
        "minFrameKb": min_kb,
        "maxFrameKb": max_kb,
        "testMb": round(test_bytes / (1024 * 1024), 2),
        "workerDirs": len(worker_dirs),
        "workerMb": round(worker_bytes / (1024 * 1024), 2),
        "audioMb": round(audio_bytes / (1024 * 1024), 2),
        "capsMb": round(caps_bytes / (1024 * 1024), 2),
        "mp4Mb": round(mp4_bytes / (1024 * 1024), 1),
        "anomalies": anomalies[:40],
        "anomalyCount": len(anomalies),
    }


def format_duration(seconds: float) -> str:
    """Format seconds as Xh Ym Zs or Ym Zs."""
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {sec:02d}s"
    return f"{m}m {sec:02d}s"


def _get_ram_gb() -> float:
    """Return total physical RAM in GiB (0.0 if unknown)."""
    try:
        if os.name == "nt":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            mem = MEMORYSTATUSEX()
            mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                return round(mem.ullTotalPhys / (1024 ** 3), 1)
        elif hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names and "SC_PHYS_PAGES" in os.sysconf_names:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return round((pages * page_size) / (1024 ** 3), 1)
    except Exception:
        pass
    return 0.0


def _short_gpu_label(name: str) -> str:
    """Compact GPU display name for UI toggle buttons."""
    cleaned = name
    for prefix in ("NVIDIA GeForce ", "NVIDIA ", "AMD Radeon(TM) ", "AMD Radeon ", "Intel(R) ", "Intel "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    for suffix in (" Laptop GPU", " Graphics"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return cleaned.strip()[:22] or name[:22]


def _gpu_score(name: str) -> int:
    """Rank discrete GPUs above integrated adapters."""
    low = name.lower()
    if any(k in low for k in ("rtx", "gtx", "quadro", "tesla", "radeon rx", "arc ", "apple m")):
        return 3
    if any(k in low for k in ("nvidia", "radeon pro", "vega")):
        return 2
    if any(k in low for k in ("radeon", "iris", "uhd", "hd graphics")):
        return 1
    return 0


def probe_nvenc_working() -> tuple[bool, str]:
    """Probe if h264_nvenc actually runs on this GPU and driver version."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        res = subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=32x32:d=0.04",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, text=True, timeout=3, creationflags=flags,
        )
        if res.returncode == 0:
            return True, "Supported"
        err = res.stderr.strip()
        if "Driver does not support" in err:
            m = re.search(r"Required:\s*([0-9.]+)\s*Found:\s*([0-9.]+)", err)
            if m:
                return False, f"Driver API {m.group(2)} < required {m.group(1)}"
            return False, "Driver update required"
        return False, "NVENC unavailable"
    except Exception as exc:
        return False, str(exc)


def detect_system_info() -> dict:
    """Inspect CPU, GPU, RAM, VRAM, NVENC, and compute safe worker limits."""
    logical_cores = os.cpu_count() or 4
    physical_cores = 0
    cpu_name = platform.processor() or platform.machine() or "CPU"
    ram_gb = _get_ram_gb()
    gpus: list[dict] = []

    if os.name == "nt":
        ps = (
            "ConvertTo-Json -Compress @{"
            "cpu=(Get-CimInstance Win32_Processor | Select-Object -First 1 Name,NumberOfCores,NumberOfLogicalProcessors);"
            "gpus=@(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM)"
            "}"
        )
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=6,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if r.returncode == 0 and r.stdout.strip():
                data = json.loads(r.stdout.strip())
                cpu_obj = data.get("cpu") or {}
                if cpu_obj.get("Name"):
                    cpu_name = " ".join(str(cpu_obj["Name"]).split())
                if cpu_obj.get("NumberOfCores"):
                    physical_cores = int(cpu_obj["NumberOfCores"])
                if cpu_obj.get("NumberOfLogicalProcessors"):
                    logical_cores = int(cpu_obj["NumberOfLogicalProcessors"])
                raw_gpus = data.get("gpus") or []
                if isinstance(raw_gpus, dict):
                    raw_gpus = [raw_gpus]
                for g in raw_gpus:
                    gname = (g.get("Name") or "").strip()
                    if not gname or "basic display" in gname.lower():
                        continue
                    adap = g.get("AdapterRAM")
                    vram = round(int(adap) / (1024 ** 3), 1) if adap else None
                    gpus.append({"name": gname, "vramGb": vram})
        except Exception:
            pass
    elif sys.platform == "darwin":
        try:
            b = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=3)
            if b.returncode == 0 and b.stdout.strip():
                cpu_name = b.stdout.strip()
            pc = subprocess.run(["sysctl", "-n", "hw.physicalcpu"], capture_output=True, text=True, timeout=3)
            if pc.returncode == 0 and pc.stdout.strip().isdigit():
                physical_cores = int(pc.stdout.strip())
        except Exception:
            pass
    else:
        try:
            for line in pathlib.Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.lower().startswith("model name"):
                    cpu_name = line.split(":", 1)[1].strip()
                    break
        except Exception:
            pass

    # Query nvidia-smi for exact NVIDIA VRAM (WMI AdapterRAM caps at 4 GiB)
    try:
        ns = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if ns.returncode == 0 and ns.stdout.strip():
            for line in ns.stdout.strip().splitlines():
                parts = [x.strip() for x in line.split(",")]
                if len(parts) >= 2:
                    nv_name = parts[0]
                    nv_vram = round(float(parts[1]) / 1024.0, 1)
                    matched = False
                    for g in gpus:
                        if nv_name.lower() in g["name"].lower() or g["name"].lower() in nv_name.lower():
                            g["vramGb"] = nv_vram
                            matched = True
                    if not matched:
                        gpus.append({"name": nv_name, "vramGb": nv_vram})
    except Exception:
        pass

    gpus.sort(key=lambda g: (_gpu_score(g["name"]), g["vramGb"] or 0.0), reverse=True)
    primary = gpus[0] if gpus else None
    primary_gpu = primary["name"] if primary else "None detected"
    vram_gb = primary["vramGb"] if primary else None

    low_gpu = primary_gpu.lower()
    if "nvidia" in low_gpu or "rtx" in low_gpu or "gtx" in low_gpu:
        gpu_vendor = "nvidia"
    elif "amd" in low_gpu or "radeon" in low_gpu:
        gpu_vendor = "amd"
    elif "intel" in low_gpu:
        gpu_vendor = "intel"
    elif "apple" in low_gpu:
        gpu_vendor = "apple"
    else:
        gpu_vendor = "unknown"

    has_nvenc, nvenc_status = probe_nvenc_working() if gpu_vendor == "nvidia" else (False, "Not an NVIDIA GPU")

    ram_cap = max(1, int((ram_gb - 2.0) / 0.8)) if ram_gb > 2.5 else logical_cores
    max_workers = max(1, min(logical_cores, ram_cap, 24))

    is_discrete = primary is not None and _gpu_score(primary_gpu) >= 2
    if primary is None:
        rec_gpu = 1
    elif is_discrete:
        vram_cap = max(1, int((vram_gb or 4.0) / 1.2))
        cap = 6 if (vram_gb or 0.0) >= 8.0 else 4
        rec_gpu = max(1, min(max_workers, vram_cap, cap))
    else:
        rec_gpu = max(1, min(max_workers, 2))

    rec_cpu = max(1, min(max_workers, max(1, logical_cores // 2), 8))

    return {
        "cpuName": cpu_name,
        "physicalCores": physical_cores or max(1, logical_cores // 2),
        "logicalCores": logical_cores,
        "ramGb": ram_gb,
        "gpus": gpus,
        "primaryGpu": primary_gpu,
        "gpuShort": _short_gpu_label(primary_gpu) if primary else "None",
        "gpuVendor": gpu_vendor,
        "vramGb": vram_gb,
        "hasGpu": primary is not None,
        "hasNvenc": has_nvenc,
        "nvencStatus": nvenc_status,
        "maxWorkers": max_workers,
        "recommendedGpuWorkers": rec_gpu,
        "recommendedCpuWorkers": rec_cpu,
    }


class RenderController:
    """Thread-safe controller managing films, rendering, encoding, and logs."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.system_info = detect_system_info()
        self.extra_films: list[pathlib.Path] = []
        self.logs: list[str] = []
        self.running: str | None = None
        self.active_film_id: str | None = None
        self.proc: subprocess.Popen | None = None
        self.stop_requested = False
        self.run_start_time: float | None = None
        self.run_start_frames = 0
        self.last_error = ""
        self.encode_progress = {
            "frame": 0,
            "total": 0,
            "pct": 0.0,
            "fps": "0",
            "speed": "0x",
        }

    def log(self, msg: str) -> None:
        line = msg.rstrip("\r\n")
        if not line:
            return
        with self.lock:
            self.logs.append(line)
            if len(self.logs) > 1200:
                self.logs = self.logs[-900:]

    def film_map(self) -> dict[str, pathlib.Path]:
        return {str(p): p for p in discover_films(self.extra_films)}

    def resolve_film(self, film_id: str | None) -> pathlib.Path | None:
        fmap = self.film_map()
        if not fmap:
            return None
        if film_id and film_id in fmap:
            return fmap[film_id]
        if self.active_film_id and self.active_film_id in fmap:
            return fmap[self.active_film_id]
        return next(iter(fmap.values()))

    def get_state(self, film_id: str | None, log_offset: int) -> dict:
        films = discover_films(self.extra_films)
        chosen = self.resolve_film(film_id)
        if chosen is not None and self.running is None:
            self.active_film_id = str(chosen)

        film_list = [{"id": str(p), "name": p.name} for p in films]
        cur_payload = None
        meta_left = ""
        meta_right = ""
        rate_val = 0.0
        eta_val = None
        elapsed_val = None

        if chosen is not None:
            info = read_film_info(chosen)
            total = info["total_frames"]
            out_dir = chosen / "final_v1"
            scan = scan_frames(out_dir, total)
            done = scan["done"]
            latest_idx = scan["latestIdx"]
            latest_path = scan["latestPath"]

            test_dir = chosen / "test_gpu"
            test_frames = scan_test_frames(test_dir)

            mp4_path = chosen / info["output"]
            mp4_exists = mp4_path.is_file()
            mtime = scan["latestMtime"]

            cur_payload = {
                "id": str(chosen),
                "name": chosen.name,
                "title": info["title"],
                "totalFrames": total,
                "output": info["output"],
                "done": done,
                "mp4Exists": mp4_exists,
                "latestFrame": latest_idx,
                "latestFrameMtime": mtime,
                "renderedFrames": scan["frames"],
                "missingCount": scan["missingCount"],
                "missingSamples": scan["missingSamples"],
                "missingRanges": scan.get("missingRanges", []),
                "testFrames": test_frames,
                "hasAudio": (chosen / "audio" / "mix.wav").is_file(),
                "hasCaptions": (chosen / "caps" / "list.txt").is_file(),
            }

            if self.running == "render" and self.run_start_time is not None:
                elapsed = time.time() - self.run_start_time
                elapsed_val = round(elapsed, 1)
                gained = max(0, done - self.run_start_frames)
                rate = gained / elapsed if elapsed > 1.0 and gained > 0 else 0.0
                rate_val = round(rate, 2)
                rem = max(0, total - done)
                meta_left = f"Elapsed {format_duration(elapsed)}"
                if rate > 0:
                    eta_sec = rem / rate
                    eta_val = round(eta_sec, 1)
                    meta_right = f"{rate:.2f} fps · ETA {format_duration(eta_sec)}"
                else:
                    meta_right = "Estimating ETA..."
            elif self.running == "encode":
                ep = self.encode_progress
                meta_left = f"Encoding: {ep['pct']:.1f}% ({ep['frame']}/{ep['total']})"
                meta_right = f"{ep['fps']} fps · {ep['speed']}"
            elif done > 0 and done < total:
                meta_left = f"Saved in {chosen.name}\\final_v1"
                meta_right = f"{total - done:,} frames left"
            elif mp4_exists:
                mp4_mb = mp4_path.stat().st_size / (1024 * 1024)
                meta_left = f"Saved: {info['output']}"
                meta_right = f"{mp4_mb:.1f} MB"

        with self.lock:
            new_logs = self.logs[max(0, log_offset):]
            err = self.last_error
            running = self.running
            encode_prog = dict(self.encode_progress)

        return {
            "films": film_list,
            "selectedFilm": str(chosen) if chosen else "",
            "current": cur_payload,
            "running": running,
            "metaLeft": meta_left,
            "metaRight": meta_right,
            "renderMetrics": {
                "fps": rate_val,
                "eta": eta_val,
                "elapsed": elapsed_val,
            },
            "logs": new_logs,
            "lastError": err,
            "system": self.system_info,
            "encodeProgress": encode_prog,
            "videoCount": len(discover_all_mp4s(self.extra_films)),
        }

    def add_folder(self) -> str | None:
        """Open a native folder picker in an isolated subprocess to avoid COM/GUI thread issues."""
        code = (
            "import tkinter as tk; from tkinter import filedialog; "
            "r=tk.Tk(); r.withdraw(); r.attributes('-topmost', True); "
            "print(filedialog.askdirectory(title='Select Film Folder (containing film.json)'))"
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        res = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, creationflags=flags)
        chosen = res.stdout.strip()
        if not chosen:
            return None
        p = pathlib.Path(chosen).resolve()
        if not (p / "film.json").is_file() or not (p / "engine" / "web").is_dir():
            raise ValueError("Selected folder must contain film.json and engine/web/.")
        if p not in self.extra_films and p.parent != FILMS_DIR.resolve():
            self.extra_films.append(p)
        self.active_film_id = str(p)
        return str(p)

    def browse_zip(self) -> str | None:
        """Open a native file picker for .zip archives in an isolated subprocess."""
        code = (
            "import tkinter as tk; from tkinter import filedialog; "
            "r=tk.Tk(); r.withdraw(); r.attributes('-topmost', True); "
            "print(filedialog.askopenfilename(title='Select Skies Film Zip Archive', filetypes=[('Zip Archives', '*.zip'), ('All Files', '*.*')]))"
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        res = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, creationflags=flags)
        chosen = res.stdout.strip()
        return chosen if chosen else None

    def import_film_zip(
        self,
        zip_source: pathlib.Path | str | bytes | io.BytesIO,
        auto_render: bool = False,
        mode: str = "gpu",
        procs: int = 4,
        w: int = 540,
        ms: int = 1,
        sm: int = 2048,
        auto_encode: bool = True,
        nvenc: bool = False,
        crf: int = 17,
    ) -> dict:
        target_dir, meta, validation = extract_film_zip(zip_source, FILMS_DIR)
        self.active_film_id = str(target_dir)
        title = meta.get("title", target_dir.name)
        self.log(f"Imported film archive: '{title}' ({target_dir.name}) -> {target_dir}")

        rendered = False
        if auto_render:
            self.log(f"Auto-render requested for '{title}': starting {mode.upper()} render...")
            self.start_render(
                film_id=str(target_dir),
                mode=mode,
                procs=procs,
                w=w,
                ms=ms,
                sm=sm,
                auto_encode=auto_encode,
                encode_nvenc=nvenc,
                encode_crf=crf,
            )
            rendered = True

        return {
            "ok": True,
            "film": str(target_dir),
            "slug": target_dir.name,
            "title": title,
            "totalFrames": meta.get("total_frames", 0),
            "output": meta.get("output", f"{target_dir.name}.mp4"),
            "validation": validation,
            "autoRendering": rendered,
        }

    def _apply_mode(self, mode: str) -> None:
        src = TOOLS_RENDER / ("run.js.gpu" if mode == "gpu" else "run.js.cpu")
        dst = TOOLS_RENDER / "run.js"
        if src.is_file():
            shutil.copyfile(src, dst)

    def _kill_proc_tree(self) -> None:
        p = self.proc
        if p is None or p.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(p.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                p.kill()

    def _run_cmd(self, cmd: list[str]) -> int:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            creationflags=flags,
        )
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line_str = line.strip()
            if line_str.startswith("ENCODE_PROGRESS"):
                # Parse progress: ENCODE_PROGRESS frame=... total=... pct=... fps=... speed=...
                parts = line_str.split()
                with self.lock:
                    for part in parts[1:]:
                        if "=" in part:
                            k, v = part.split("=", 1)
                            if k == "frame":
                                self.encode_progress["frame"] = int(v)
                            elif k == "total":
                                self.encode_progress["total"] = int(v)
                            elif k == "pct":
                                self.encode_progress["pct"] = float(v.rstrip("%"))
                            elif k == "fps":
                                self.encode_progress["fps"] = v
                            elif k == "speed":
                                self.encode_progress["speed"] = v
            else:
                self.log(line)
        rc = self.proc.wait()
        self.proc = None
        return rc

    def start_render(
        self,
        film_id: str | None,
        mode: str,
        procs: int,
        w: int,
        ms: int,
        sm: int,
        custom_range: str | None = None,
        only_missing: bool = False,
        auto_encode: bool = False,
        encode_nvenc: bool = False,
        encode_crf: int = 17,
        encode_output_name: str | None = None,
    ) -> None:
        with self.lock:
            if self.running is not None:
                raise RuntimeError("A task is already running.")
            film = self.resolve_film(film_id)
            if film is None:
                raise ValueError("No valid film selected.")
            info = read_film_info(film)
            total = info["total_frames"]
            out_dir = film / "final_v1"
            rescued = rescue_worker_frames(out_dir)
            if rescued:
                self.logs.append(f"Rescued {rescued} completed worker frames.")
            scan = scan_frames(out_dir, total)
            done = scan["done"]

            if done >= total and not custom_range and not only_missing:
                raise ValueError("All frames are already rendered. Click Encode MP4 instead.")

            self.active_film_id = str(film)
            self.running = "render"
            self.stop_requested = False
            self.last_error = ""
            self.run_start_time = time.time()
            self.run_start_frames = done

        self._apply_mode(mode)
        procs = max(1, min(self.system_info["maxWorkers"], int(procs)))

        target_range = None
        list_arg = None
        if only_missing:
            missing = [i for i in range(total) if i not in scan["frames"]]
            if not missing:
                with self.lock:
                    self.running = None
                self.log("No missing frames found.")
                return
            list_arg = ",".join(map(str, missing))
            self.log(f"Rendering {len(missing)} missing frames on {mode.upper()}...")
        elif custom_range and custom_range.strip():
            target_range, list_arg = parse_frame_spec(custom_range, total)
            self.log(f"Starting {mode.upper()} render for {film.name} (selection: {custom_range.strip()}, workers={procs}, w={w}, ms={ms}, sm={sm})")
        else:
            target_range = f"0-{total - 1}"
            self.log(f"Starting {mode.upper()} render for {film.name} ({done}/{total} done, workers={procs}, w={w}, ms={ms}, sm={sm})")

        def worker() -> None:
            should_encode = False
            try:
                attempt = 1
                while not self.stop_requested:
                    cmd = [
                        sys.executable, "-u", str(TOOLS_RENDER / "render.py"),
                        "--web", str(film / "engine" / "web"),
                        "--out", str(out_dir),
                        "--w", str(w), "--procs", str(procs),
                        "--ms", str(ms), "--sm", str(sm),
                        "--mode", mode,
                    ]
                    if list_arg:
                        cmd.extend(["--list", list_arg])
                    else:
                        cmd.extend(["--range", target_range])

                    self._run_cmd(cmd)
                    rescue_worker_frames(out_dir)

                    scan_now = scan_frames(out_dir, total)
                    done_now = scan_now["done"]

                    if only_missing or custom_range or done_now >= total or self.stop_requested:
                        if done_now >= total:
                            self.log(f"All {total} frames complete.")
                            if auto_encode and not self.stop_requested:
                                should_encode = True
                        elif self.stop_requested:
                            self.log(f"Stopped safely at {done_now}/{total} frames.")
                        break

                    attempt += 1
                    self.log(f"Pass {attempt} stopped at {done_now}/{total}; resuming remaining frames...")
                    time.sleep(2)

                if should_encode:
                    self.log("Auto-Encode enabled: starting MP4 encode automatically...")
                    self._run_encode_sync(
                        film,
                        info,
                        out_dir,
                        total,
                        encode_nvenc,
                        crf=encode_crf,
                        cq=encode_crf + 1,
                        output_name=encode_output_name,
                    )
            except Exception as exc:
                with self.lock:
                    self.last_error = str(exc)
                self.log(f"Error: {exc}")
            finally:
                with self.lock:
                    self.running = None
                    self.run_start_time = None

        threading.Thread(target=worker, daemon=True).start()

    def start_test(self, film_id: str | None, w: int, ms: int, sm: int) -> None:
        with self.lock:
            if self.running is not None:
                raise RuntimeError("A task is already running.")
            film = self.resolve_film(film_id)
            if film is None:
                raise ValueError("No valid film selected.")
            info = read_film_info(film)
            total = info["total_frames"]
            start = min(200, max(0, total - 5))
            sample = [str(i) for i in range(start, min(total, start + 5))] or ["0"]
            self.active_film_id = str(film)
            self.running = "test"
            self.stop_requested = False
            self.last_error = ""

        self._apply_mode("gpu")
        test_out = film / "test_gpu"
        self.log(f"Running 5-frame GPU test ({','.join(sample)}) -> {test_out}")

        def worker() -> None:
            try:
                shutil.rmtree(test_out, ignore_errors=True)
                cmd = [
                    sys.executable, "-u", str(TOOLS_RENDER / "render.py"),
                    "--web", str(film / "engine" / "web"),
                    "--out", str(test_out),
                    "--list", ",".join(sample),
                    "--w", str(w), "--procs", "1",
                    "--ms", str(ms), "--sm", str(sm),
                    "--mode", "gpu",
                ]
                self._run_cmd(cmd)
                rescue_worker_frames(test_out)
                self.log("GPU test frames complete.")
            except Exception as exc:
                with self.lock:
                    self.last_error = str(exc)
                self.log(f"Test error: {exc}")
            finally:
                with self.lock:
                    self.running = None

        threading.Thread(target=worker, daemon=True).start()

    def _run_encode_sync(
        self,
        film: pathlib.Path,
        info: dict,
        out_dir: pathlib.Path,
        total: int,
        nvenc: bool,
        crf: int = 17,
        cq: int = 18,
        output_name: str | None = None,
    ) -> None:
        crf = max(10, min(32, int(crf)))
        cq = max(10, min(32, int(cq)))
        raw_name = (output_name or "").strip()
        if raw_name:
            safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name)
            if not safe_name.lower().endswith(".mp4"):
                safe_name += ".mp4"
        else:
            safe_name = info["output"]

        with self.lock:
            self.running = "encode"
            self.encode_progress = {
                "frame": 0,
                "total": total,
                "pct": 0.0,
                "fps": "0",
                "speed": "0x",
            }

        out_mp4 = film / safe_name
        self.log(f"Encoding {safe_name} ({'NVENC GPU' if nvenc else 'libx264 CPU'}, quality CRF {crf}/CQ {cq})...")

        cmd = [
            sys.executable, "-u", str(TOOLS_RENDER / "encode.py"),
            str(out_dir), str(total),
            str(film / "audio" / "mix.wav"),
            str(film / "caps"),
            str(out_mp4),
            "--crf", str(crf),
            "--cq", str(cq),
        ]
        if nvenc:
            cmd.append("--nvenc")
        rc = self._run_cmd(cmd)
        status = "Completed" if rc == 0 else "Failed"
        if rc != 0 and not self.stop_requested:
            with self.lock:
                self.last_error = f"Encode failed with exit code {rc}. Check activity log."
        else:
            self.log(f"Successfully encoded {out_mp4.name}!")

        size_str = f"{round(out_mp4.stat().st_size / (1024 * 1024), 1)} MB" if out_mp4.is_file() else "0 MB"
        record_encode_history({
            "id": f"enc_{int(time.time())}",
            "filmName": film.name,
            "filmTitle": info["title"],
            "filename": out_mp4.name,
            "filePath": str(out_mp4.resolve()),
            "encoder": "h264_nvenc" if nvenc else "libx264",
            "totalFrames": total,
            "duration": f"{total / 30.0:.1f}s",
            "sizeMb": size_str,
            "timestamp": int(time.time() * 1000),
            "date": time.strftime("%b %d, %Y %I:%M %p"),
            "status": status,
        })

    def start_encode(
        self,
        film_id: str | None,
        nvenc: bool,
        crf: int = 17,
        cq: int = 18,
        output_name: str | None = None,
    ) -> None:
        with self.lock:
            if self.running is not None:
                raise RuntimeError("A task is already running.")
            film = self.resolve_film(film_id)
            if film is None:
                raise ValueError("No valid film selected.")
            info = read_film_info(film)
            total = info["total_frames"]
            out_dir = film / "final_v1"
            rescue_worker_frames(out_dir)
            scan = scan_frames(out_dir, total)
            if scan["done"] < total:
                raise ValueError(f"Only {scan['done']}/{total} frames rendered ({scan['missingCount']} missing). Finish rendering first.")
            self.active_film_id = str(film)
            self.running = "encode"
            self.stop_requested = False
            self.last_error = ""

        def worker() -> None:
            try:
                self._run_encode_sync(film, info, out_dir, total, nvenc, crf=crf, cq=cq, output_name=output_name)
            except Exception as exc:
                with self.lock:
                    self.last_error = str(exc)
                self.log(f"Encode error: {exc}")
            finally:
                with self.lock:
                    self.running = None

        threading.Thread(target=worker, daemon=True).start()

    def stop(self) -> None:
        self.stop_requested = True
        self.log("Stopping active workers...")
        self._kill_proc_tree()
        if self.active_film_id:
            rescue_worker_frames(pathlib.Path(self.active_film_id) / "final_v1")


def make_handler(ctrl: RenderController):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0:
                return {}
            return json.loads(self.rfile.read(n).decode("utf-8"))

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/":
                data = GUI_HTML.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            if parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return

            if parsed.path == "/api/state":
                film = qs.get("film", [None])[0]
                offset = int(qs.get("logOffset", ["0"])[0])
                self._send_json(ctrl.get_state(film, offset))
                return

            if parsed.path == "/api/validate":
                film_id = qs.get("film", [None])[0]
                film = ctrl.resolve_film(film_id)
                if film is None:
                    self._send_json({"error": "No film found"}, 404)
                    return
                self._send_json(validate_film(film))
                return

            if parsed.path == "/api/preview":
                film_id = qs.get("film", [None])[0]
                film = ctrl.resolve_film(film_id)
                if film is None:
                    self.send_error(404)
                    return

                source = qs.get("source", ["final"])[0]
                frame_req = qs.get("frame", [None])[0]

                target_file: pathlib.Path | None = None
                if source == "test":
                    test_dir = film / "test_gpu"
                    if frame_req is not None and frame_req.isdigit():
                        candidate = test_dir / ("f_%05d.png" % int(frame_req))
                        if candidate.is_file():
                            target_file = candidate
                    if target_file is None and test_dir.is_dir():
                        frames = sorted(test_dir.glob("f_*.png"))
                        if frames:
                            target_file = frames[-1]
                else:
                    out_dir = film / "final_v1"
                    if frame_req is not None and frame_req.isdigit():
                        idx = int(frame_req)
                        candidate = out_dir / ("f_%05d.png" % idx)
                        if candidate.is_file():
                            target_file = candidate
                        else:
                            for d in out_dir.glob("_w*"):
                                c2 = d / ("f_%05d.png" % idx)
                                if c2.is_file():
                                    target_file = c2
                                    break
                    if target_file is None:
                        info = read_film_info(film)
                        scan = scan_frames(out_dir, info["total_frames"])
                        if scan["latestPath"]:
                            target_file = pathlib.Path(scan["latestPath"])

                if target_file is None or not target_file.is_file():
                    self.send_error(404)
                    return

                try:
                    data = target_file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except Exception:
                    self.send_error(404)
                return

            if parsed.path == "/api/library":
                videos = discover_all_mp4s(ctrl.extra_films)
                history = get_history(ctrl.extra_films)
                self._send_json({"videos": videos, "history": history})
                return

            if parsed.path == "/api/video":
                film_id = qs.get("film", [None])[0]
                path_arg = qs.get("path", [None])[0]

                mp4_file: pathlib.Path | None = None
                if path_arg:
                    p = pathlib.Path(path_arg).resolve()
                    if p.is_file() and p.suffix.lower() == ".mp4":
                        mp4_file = p
                elif film_id:
                    film = ctrl.resolve_film(film_id)
                    if film:
                        info = read_film_info(film)
                        p = film / info["output"]
                        if p.is_file():
                            mp4_file = p

                if mp4_file is None or not mp4_file.is_file():
                    self.send_error(404)
                    return

                self._stream_media_file(mp4_file, "video/mp4")
                return

            if parsed.path == "/api/audio":
                film_id = qs.get("film", [None])[0]
                film = ctrl.resolve_film(film_id)
                wav_file = (film / "audio" / "mix.wav") if film else None
                if wav_file is None or not wav_file.is_file():
                    self.send_error(404)
                    return
                self._stream_media_file(wav_file, "audio/wav")
                return

            if parsed.path == "/api/caption":
                film_id = qs.get("film", [None])[0]
                frame_req = qs.get("frame", ["0"])[0]
                film = ctrl.resolve_film(film_id)
                if film is None or not frame_req.isdigit():
                    self.send_error(404)
                    return
                cap_file = resolve_caption_for_frame(film, int(frame_req))
                if cap_file is None or not cap_file.is_file():
                    self.send_response(204)
                    self.end_headers()
                    return
                data = cap_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            if parsed.path == "/api/waveform":
                film_id = qs.get("film", [None])[0]
                bars = max(32, min(400, int(qs.get("bars", ["200"])[0])))
                film = ctrl.resolve_film(film_id)
                if film is None:
                    self._send_json({"error": "No film found"}, 404)
                    return
                self._send_json(compute_audio_waveform(film / "audio" / "mix.wav", bars))
                return

            if parsed.path == "/api/metrics":
                film_id = qs.get("film", [None])[0]
                film = ctrl.resolve_film(film_id)
                if film is None:
                    self._send_json({"error": "No film found"}, 404)
                    return
                self._send_json(compute_film_metrics(film))
                return

            self.send_error(404)

        def _stream_media_file(self, media_file: pathlib.Path, content_type: str) -> None:
            file_size = media_file.stat().st_size
            range_header = self.headers.get("Range")

            if range_header and range_header.startswith("bytes="):
                parts = range_header[6:].split("-")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if parts[1] else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1

                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

                with open(media_file, "rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(length))
            else:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

                with open(media_file, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/api/film/upload-zip":
                try:
                    content_len = int(self.headers.get("Content-Length", 0))
                    if content_len <= 0:
                        self._send_json({"error": "No file uploaded"}, 400)
                        return
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                        tmp_path = pathlib.Path(tmp.name)
                        remaining = content_len
                        while remaining > 0:
                            chunk = self.rfile.read(min(remaining, 65536))
                            if not chunk:
                                break
                            tmp.write(chunk)
                            remaining -= len(chunk)
                    try:
                        auto_render = qs.get("autoRender", ["false"])[0].lower() in ("true", "1", "yes")
                        mode = qs.get("mode", ["gpu"])[0]
                        procs = int(qs.get("procs", ["4"])[0])
                        auto_encode = qs.get("autoEncode", ["true"])[0].lower() in ("true", "1", "yes")
                        nvenc = qs.get("nvenc", ["false"])[0].lower() in ("true", "1", "yes")
                        crf = int(qs.get("crf", ["17"])[0])
                        res = ctrl.import_film_zip(
                            tmp_path,
                            auto_render=auto_render,
                            mode=mode,
                            procs=procs,
                            auto_encode=auto_encode,
                            nvenc=nvenc,
                            crf=crf,
                        )
                        self._send_json(res)
                    finally:
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                except Exception as exc:
                    self._send_json({"error": str(exc)}, 400)
                return

            try:
                body = self._read_json()
                if self.path == "/api/film/browse-zip":
                    chosen = ctrl.browse_zip()
                    self._send_json({"selected": chosen})
                elif self.path == "/api/film/import-zip":
                    zip_path = body.get("path")
                    if not zip_path:
                        self._send_json({"error": "Path to zip file required"}, 400)
                        return
                    p = pathlib.Path(zip_path).resolve()
                    if not p.is_file():
                        self._send_json({"error": f"Zip file not found: {p}"}, 404)
                        return
                    res = ctrl.import_film_zip(
                        p,
                        auto_render=bool(body.get("autoRender", False)),
                        mode=body.get("mode", "gpu"),
                        procs=int(body.get("procs", 4)),
                        auto_encode=bool(body.get("autoEncode", True)),
                        nvenc=bool(body.get("nvenc", False)),
                        crf=int(body.get("crf", 17)),
                    )
                    self._send_json(res)
                elif self.path == "/api/browse":
                    sel = ctrl.add_folder()
                    self._send_json({"selected": sel})
                elif self.path == "/api/open-folder":
                    film = ctrl.resolve_film(body.get("film"))
                    open_path_native(film if film else ROOT)
                    self._send_json({"ok": True})
                elif self.path == "/api/open-mp4":
                    target_path = body.get("path")
                    if target_path:
                        p = pathlib.Path(target_path).resolve()
                        if p.is_file():
                            open_path_native(p)
                    else:
                        film = ctrl.resolve_film(body.get("film"))
                        if film:
                            mp4 = film / read_film_info(film)["output"]
                            if mp4.is_file():
                                open_path_native(mp4)
                    self._send_json({"ok": True})
                elif self.path == "/api/open-file":
                    p = pathlib.Path(body.get("path", "")).resolve()
                    if p.is_file() or p.is_dir():
                        open_path_native(p)
                    self._send_json({"ok": True})
                elif self.path == "/api/reveal-file":
                    target = body.get("path")
                    if target:
                        p = pathlib.Path(target).resolve()
                    else:
                        film = ctrl.resolve_film(body.get("film"))
                        p = film if film else ROOT
                    reveal_path_native(p)
                    self._send_json({"ok": True})
                elif self.path == "/api/render/start":
                    ctrl.start_render(
                        body.get("film"),
                        body.get("mode", "gpu"),
                        body.get("procs", 4),
                        body.get("w", 540),
                        body.get("ms", 1),
                        body.get("sm", 2048),
                        custom_range=body.get("range"),
                        only_missing=bool(body.get("onlyMissing", False)),
                        auto_encode=bool(body.get("autoEncode", False)),
                        encode_nvenc=bool(body.get("nvenc", False)),
                        encode_crf=int(body.get("crf", 17)),
                        encode_output_name=body.get("outputName"),
                    )
                    self._send_json({"ok": True})
                elif self.path == "/api/render/test":
                    ctrl.start_test(
                        body.get("film"),
                        body.get("w", 540),
                        body.get("ms", 1),
                        body.get("sm", 2048),
                    )
                    self._send_json({"ok": True})
                elif self.path == "/api/render/stop":
                    ctrl.stop()
                    self._send_json({"ok": True})
                elif self.path == "/api/encode/start":
                    ctrl.start_encode(
                        body.get("film"),
                        bool(body.get("nvenc", False)),
                        crf=int(body.get("crf", 17)),
                        cq=int(body.get("cq", 18)),
                        output_name=body.get("outputName"),
                    )
                    self._send_json({"ok": True})
                elif self.path == "/api/clean":
                    if ctrl.running is not None:
                        self._send_json({"error": "Cannot clean temporary folders while a job is running"}, 409)
                        return
                    film = ctrl.resolve_film(body.get("film"))
                    if film is None:
                        self._send_json({"error": "No film selected"}, 400)
                        return
                    target = body.get("target")
                    freed = 0
                    if target == "test":
                        test_dir = film / "test_gpu"
                        if test_dir.is_dir():
                            freed = sum(p.stat().st_size for p in test_dir.rglob("*") if p.is_file())
                            shutil.rmtree(test_dir, ignore_errors=True)
                    elif target == "workers":
                        out_dir = film / "final_v1"
                        if out_dir.is_dir():
                            for d in out_dir.glob("_w*"):
                                if d.is_dir():
                                    freed += sum(p.stat().st_size for p in d.rglob("*") if p.is_file())
                                    shutil.rmtree(d, ignore_errors=True)
                    else:
                        self._send_json({"error": "Unknown clean target"}, 400)
                        return
                    self._send_json({"ok": True, "freedMb": round(freed / (1024 * 1024), 2)})
                elif self.path == "/api/video/delete":
                    target_path = body.get("path")
                    if target_path:
                        p = pathlib.Path(target_path).resolve()
                        allowed = [FILMS_DIR.resolve()] + [f.resolve() for f in ctrl.extra_films]
                        is_allowed = any(p.is_relative_to(a) for a in allowed if a.exists())
                        if is_allowed and p.is_file() and p.suffix.lower() == ".mp4":
                            p.unlink()
                            self._send_json({"ok": True, "deleted": str(p)})
                            return
                    self._send_json({"error": "Invalid or disallowed path"}, 400)
                elif self.path == "/api/history/clear":
                    try:
                        HISTORY_FILE.write_text("[]", encoding="utf-8")
                        self._send_json({"ok": True})
                    except Exception as exc:
                        self._send_json({"error": str(exc)}, 500)
                else:
                    self._send_json({"error": "Unknown endpoint"}, 404)
            except Exception as exc:
                self._send_json({"error": str(exc)}, 400)

    return Handler


def find_app_browser() -> pathlib.Path | None:
    for p in CHROME_PATHS:
        if p.is_file():
            return p
    for cmd in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        found = shutil.which(cmd)
        if found:
            return pathlib.Path(found)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--serve-only", action="store_true")
    args = ap.parse_args()

    ctrl = RenderController()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(ctrl))
    server.allow_reuse_address = True
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"

    if args.serve_only:
        print(f"SERVING {url}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            ctrl.stop()
            server.shutdown()
        return

    threading.Thread(target=server.serve_forever, daemon=True).start()
    browser = find_app_browser()
    if browser is not None:
        profile_dir = tempfile.mkdtemp(prefix="skies_gui_")
        try:
            proc = subprocess.Popen([
                str(browser),
                f"--app={url}",
                f"--user-data-dir={profile_dir}",
                "--window-size=1020,740",
                "--no-first-run",
                "--no-default-browser-check",
            ])
            proc.wait()
        finally:
            ctrl.stop()
            server.shutdown()
            shutil.rmtree(profile_dir, ignore_errors=True)
    else:
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            ctrl.stop()
            server.shutdown()


if __name__ == "__main__":
    main()
