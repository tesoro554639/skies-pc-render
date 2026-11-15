"""Local web-app backend + native Chrome app window launcher for Skies Render."""

from __future__ import annotations

import argparse
import ctypes
import http.server
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser

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
    data = json.loads((film_dir / "film.json").read_text(encoding="utf-8"))
    return {
        "name": data.get("name", film_dir.name),
        "title": data.get("title", film_dir.name),
        "total_frames": int(data["total_frames"]),
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
                shutil.move(str(f), str(target))
                moved += 1
    return moved


def scan_frames(out_dir: pathlib.Path, total: int) -> tuple[int, int, pathlib.Path | None]:
    """Return (done_count, latest_frame_idx_or_-1, latest_frame_path)."""
    if not out_dir.is_dir():
        return 0, -1, None
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
    if not seen:
        return 0, -1, None
    latest_idx = max(seen)
    return len(seen), latest_idx, seen[latest_idx]


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

    has_nvenc = False
    if gpu_vendor == "nvidia":
        try:
            ff = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            has_nvenc = "h264_nvenc" in ff.stdout
        except Exception:
            pass

    # Safe worker ceiling: bounded by logical threads and ~0.8 GB RAM per browser worker
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

    def log(self, msg: str) -> None:
        line = msg.rstrip("\r\n")
        if not line:
            return
        with self.lock:
            self.logs.append(line)
            if len(self.logs) > 1000:
                self.logs = self.logs[-800:]

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

        if chosen is not None:
            info = read_film_info(chosen)
            total = info["total_frames"]
            out_dir = chosen / "final_v1"
            done, latest_idx, latest_path = scan_frames(out_dir, total)
            mp4_exists = (chosen / info["output"]).is_file()
            mtime = int(latest_path.stat().st_mtime * 1000) if latest_path and latest_path.exists() else 0
            cur_payload = {
                "id": str(chosen),
                "name": chosen.name,
                "title": info["title"],
                "totalFrames": total,
                "output": info["output"],
                "done": done,
                "mp4Exists": mp4_exists,
                "latestFrame": latest_idx if latest_idx >= 0 else None,
                "latestFrameMtime": mtime,
            }
            if self.running == "render" and self.run_start_time is not None:
                elapsed = time.time() - self.run_start_time
                gained = max(0, done - self.run_start_frames)
                rate = gained / elapsed if elapsed > 1.0 and gained > 0 else 0.0
                rem = max(0, total - done)
                meta_left = f"Elapsed {format_duration(elapsed)}"
                if rate > 0:
                    meta_right = f"{rate:.2f} fps · ETA {format_duration(rem / rate)}"
                else:
                    meta_right = "Estimating ETA..."
            elif done > 0 and done < total:
                meta_left = f"Saved in {chosen.name}\\final_v1"
                meta_right = f"{total - done:,} frames left"
            elif mp4_exists:
                mp4_mb = (chosen / info["output"]).stat().st_size / (1024 * 1024)
                meta_left = f"Saved: {info['output']}"
                meta_right = f"{mp4_mb:.1f} MB"

        with self.lock:
            new_logs = self.logs[max(0, log_offset):]
            err = self.last_error
            running = self.running

        return {
            "films": film_list,
            "selectedFilm": str(chosen) if chosen else "",
            "current": cur_payload,
            "running": running,
            "metaLeft": meta_left,
            "metaRight": meta_right,
            "logs": new_logs,
            "lastError": err,
            "system": self.system_info,
        }

    def add_folder(self) -> str | None:
        """Open a native folder picker in an isolated subprocess to avoid COM/GUI thread issues."""
        code = (
            "import tkinter as tk; from tkinter import filedialog; "
            "r=tk.Tk(); r.withdraw(); r.attributes('-topmost', True); "
            "print(filedialog.askdirectory(title='Select Film Folder (containing film.json)'))"
        )
        res = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True)
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
            )
        else:
            p.terminate()

    def _run_cmd(self, cmd: list[str]) -> int:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
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
            self.log(line)
        rc = self.proc.wait()
        self.proc = None
        return rc

    def start_render(self, film_id: str | None, mode: str, procs: int, w: int, ms: int, sm: int) -> None:
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
            done, _, _ = scan_frames(out_dir, total)
            if done >= total:
                raise ValueError("All frames are already rendered. Click Encode MP4 instead.")

            self.active_film_id = str(film)
            self.running = "render"
            self.stop_requested = False
            self.last_error = ""
            self.run_start_time = time.time()
            self.run_start_frames = done

        self._apply_mode(mode)
        procs = max(1, min(self.system_info["maxWorkers"], int(procs)))
        self.log(f"Starting {mode.upper()} render for {film.name} ({done}/{total} done, workers={procs}, w={w}, ms={ms}, sm={sm})")

        def worker() -> None:
            try:
                for attempt in range(1, 6):
                    if self.stop_requested:
                        break
                    cmd = [
                        sys.executable, "-u", str(TOOLS_RENDER / "render.py"),
                        "--web", str(film / "engine" / "web"),
                        "--out", str(out_dir),
                        "--range", f"0-{total - 1}",
                        "--w", str(w), "--procs", str(procs),
                        "--ms", str(ms), "--sm", str(sm),
                    ]
                    self._run_cmd(cmd)
                    moved = rescue_worker_frames(out_dir)
                    if moved:
                        self.log(f"Rescued {moved} frames from worker folders.")
                    done_now, _, _ = scan_frames(out_dir, total)
                    if done_now >= total:
                        self.log(f"All {total} frames complete. Ready to encode MP4.")
                        break
                    if self.stop_requested:
                        self.log(f"Stopped safely at {done_now}/{total} frames.")
                        break
                    self.log(f"Pass {attempt} stopped at {done_now}/{total}; resuming remaining frames...")
                    time.sleep(2)
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
                ]
                self._run_cmd(cmd)
            except Exception as exc:
                with self.lock:
                    self.last_error = str(exc)
                self.log(f"Test error: {exc}")
            finally:
                with self.lock:
                    self.running = None

        threading.Thread(target=worker, daemon=True).start()

    def start_encode(self, film_id: str | None, nvenc: bool) -> None:
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
            done, _, _ = scan_frames(out_dir, total)
            if done < total:
                raise ValueError(f"Only {done}/{total} frames rendered. Finish rendering first.")
            self.active_film_id = str(film)
            self.running = "encode"
            self.stop_requested = False
            self.last_error = ""

        out_mp4 = film / info["output"]
        self.log(f"Encoding {info['output']} ({'NVENC GPU' if nvenc else 'libx264 CPU'})...")

        def worker() -> None:
            try:
                cmd = [
                    sys.executable, "-u", str(TOOLS_RENDER / "encode.py"),
                    str(out_dir), str(total),
                    str(film / "audio" / "mix.wav"),
                    str(film / "caps"),
                    str(out_mp4),
                ]
                if nvenc:
                    cmd.append("--nvenc")
                rc = self._run_cmd(cmd)
                if rc != 0 and not self.stop_requested:
                    with self.lock:
                        self.last_error = f"Encode failed with exit code {rc}. Check activity log."
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
            body = json.dumps(payload).encode("utf-8")
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
            if parsed.path == "/api/preview":
                film_id = qs.get("film", [None])[0]
                film = ctrl.resolve_film(film_id)
                if film is None:
                    self.send_error(404)
                    return
                info = read_film_info(film)
                _, _, path = scan_frames(film / "final_v1", info["total_frames"])
                if path is None or not path.is_file():
                    self.send_error(404)
                    return
                data = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            try:
                body = self._read_json()
                if self.path == "/api/browse":
                    sel = ctrl.add_folder()
                    self._send_json({"selected": sel})
                elif self.path == "/api/open-folder":
                    film = ctrl.resolve_film(body.get("film"))
                    os.startfile(str(film if film else ROOT))
                    self._send_json({"ok": True})
                elif self.path == "/api/open-mp4":
                    film = ctrl.resolve_film(body.get("film"))
                    if film:
                        mp4 = film / read_film_info(film)["output"]
                        if mp4.is_file():
                            os.startfile(str(mp4))
                    self._send_json({"ok": True})
                elif self.path == "/api/render/start":
                    ctrl.start_render(
                        body.get("film"),
                        body.get("mode", "gpu"),
                        body.get("procs", 4),
                        body.get("w", 540),
                        body.get("ms", 1),
                        body.get("sm", 2048),
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
                    ctrl.start_encode(body.get("film"), bool(body.get("nvenc", False)))
                    self._send_json({"ok": True})
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
                "--window-size=940,660",
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
