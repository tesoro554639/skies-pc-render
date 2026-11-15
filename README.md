# Skies PC Render

Local GPU/CPU frame renderer, live monitor GUI, and MP4 encoder for Skies WebGL films.

---

## Requirements

This bundle already includes `tools/render/node_modules` and configuration files. On your machine, you need:

- **Python 3** (`python` / `pythonw` on Windows, `python3` on Linux/macOS)
- **Node.js** (with Playwright — already installed in `tools/render/node_modules`)
- **Google Chrome, Microsoft Edge, or Playwright Chromium** (used headless for WebGL rendering and `--app` mode for the GUI)
- **FFmpeg & FFprobe** (`ffmpeg` and `ffprobe` on `PATH` for MP4 encoding and NVENC detection)

---

## Option 1: Using the Desktop GUI (Recommended)

Double-click **`launch_gui.bat`** (or run `python gui.py` from a terminal).

1. **Select a Film**: Choose a film from the top-left dropdown (auto-discovered from `films/`), or click **Add folder** to select any film folder containing `film.json` and `engine/web/`.
2. **Choose Render Device**: Toggle **GPU** (hardware WebGL via ANGLE Direct3D 11) or **CPU** (software WebGL via SwiftShader) in the top-right.
3. **Test First (Optional)**: Expand **Render settings & test** and click **Test 5 frames (GPU)** to render 5 sample frames into `<film>/test_gpu/` and verify your GPU works properly.
4. **Adjust Workers & Quality (Optional)**:
   - **Workers**: Auto-recommended based on your CPU cores, RAM, and GPU VRAM. Lower this if you experience high memory usage or crashes.
   - **Render settings & test**: Configure render **Width** (`540`, `720`, or `1080` px in 9:16 portrait), **MSAA** (`1x`, `2x`, `4x`), and **Shadow map** (`1024`, `2048`, `4096`).
5. **Render Frames**: Click **Start Render**.
   - Shows live latest-frame preview, frame count, FPS, and ETA.
   - Click **Stop Safely** at any time—completed frames are preserved in `<film>/final_v1/` and skipped automatically when you resume.
6. **Encode MP4**: Once all frames are rendered, optionally check **Use GPU video encoder (NVENC)** (if supported by your GPU/FFmpeg) and click **Encode MP4**. When finished, click **Open MP4** or **Open folder** to view the output video.

> **Headless / Browser-only GUI mode:** Run `python gui.py --serve-only --port 8080` to serve the web UI without launching a standalone app window.

---

## Option 2: Using the Command-Line / Batch Scripts

All scripts run from the repository root and default to `films/knocker-upper` when no film argument is provided.

### Step 1 — Test the GPU (Windows)

Double-click **`test_gpu.bat`**.
- Renders 5 test frames (`200,201,202,203,204`) into `films\knocker-upper\test_gpu\` at `540` px width with 1 worker.
- Check Task Manager → Performance → GPU to confirm GPU activity, and inspect the PNGs in `test_gpu\`.

### Step 2 — Render All Frames

- **Windows (GPU mode):** Double-click **`run_gpu.bat`** (copies `tools\render\run.js.gpu` to `tools\render\run.js` and starts `run_loop.py`).
- **Windows (CPU fallback):** Double-click **`run_cpu.bat`** (switches to SwiftShader software rendering via `run.js.cpu` and starts `run_loop.py`).
- **Windows (current mode, custom film):**
  ```bat
  render.bat knocker-upper
  ```
- **Linux / macOS:**
  ```bash
  ./render.sh knocker-upper
  ```
- **Direct Python:**
  ```bash
  python run_loop.py films/knocker-upper
  ```

`run_loop.py` automatically runs `tools/render/render.py` across all logical CPU cores, rescues completed frames from worker subfolders (`_w0`, `_w1`, ...) into `final_v1/`, and skips already-rendered `f_NNNNN.png` files. You can stop (`Ctrl+C`) and restart at any time without losing progress.

### Step 3 — Encode the Final MP4

Once all frames (`0` to `total_frames - 1`) are in `final_v1/`:

- **Windows:** Double-click **`encode.bat`** (or run `encode.bat <film-name>`).
- **Linux / macOS:**
  ```bash
  ./encode.sh knocker-upper
  ```
- **Direct Python:**
  ```bash
  python encode_film.py films/knocker-upper
  ```
- **Direct Encoder with NVENC (GPU H.264):**
  ```bash
  python tools/render/encode.py films/knocker-upper/final_v1 1129 films/knocker-upper/audio/mix.wav films/knocker-upper/caps films/knocker-upper/Before-Alarm-Clocks-Knocker-Upper_1080p.mp4 --nvenc
  ```

The encoder upscales frames to `1080x1920` (Lanczos) at `30 fps`, overlays captions from `caps/list.txt`, muxes `audio/mix.wav` (padded/trimmed to `total_frames / 30` seconds), and outputs H.264 (`libx264` CRF 17 or `h264_nvenc` CQ 18) + AAC `256k` audio.

---

## Project Structure

```text
.
├── launch_gui.bat          # Launches the local desktop GUI (gui.py)
├── gui.py                  # Local HTTP server + Chrome/Edge app-window launcher
├── test_gpu.bat            # Renders 5 test frames on GPU (knocker-upper)
├── run_gpu.bat             # Switches to GPU mode and starts render loop
├── run_cpu.bat             # Switches to CPU (SwiftShader) mode and starts render loop
├── render.bat / render.sh  # Runs run_loop.py for a specified film (default: knocker-upper)
├── encode.bat / encode.sh  # Runs encode_film.py for a specified film (default: knocker-upper)
├── run_loop.py             # Resumable multi-pass render loop
├── encode_film.py          # Reads film.json and invokes tools/render/encode.py
├── tools/
│   ├── gui/
│   │   └── index.html      # Web GUI frontend
│   └── render/
│       ├── render.py       # Spawns local HTTP frame servers + Playwright workers
│       ├── srv.py          # Local frame receiver server (POST /frame, /done, /log)
│       ├── encode.py       # FFmpeg upscaling, caption overlay, audio mux, H.264 encode
│       ├── run.js          # Active Playwright browser launcher (copied from .gpu or .cpu)
│       ├── run.js.gpu      # Hardware GPU (ANGLE D3D11) Playwright config
│       └── run.js.cpu      # Software CPU (SwiftShader) Playwright config
└── films/
    └── knocker-upper/
        ├── film.json       # Film metadata (name, title, total_frames, output)
        ├── engine/web/     # Built WebGL scene (index.html + assets)
        ├── audio/mix.wav   # Final audio track
        ├── caps/           # Caption PNGs + list.txt
        ├── final_v1/       # Rendered PNG frames (f_00000.png ...)
        └── test_gpu/       # 5-frame GPU test output
```

### Adding Another Film

Create a folder under `films/<your-film>/` with:
- `film.json`:
  ```json
  {
    "name": "your-film",
    "title": "Your Film Title",
    "total_frames": 1129,
    "output": "Your-Film_1080p.mp4"
  }
  ```
- `engine/web/` containing `index.html` and scene assets
- `audio/mix.wav`
- `caps/list.txt` (with caption PNGs)

It will appear automatically in the GUI film selector, or you can pass `<your-film>` to `render.bat` / `encode.bat`.

---

## Troubleshooting

- **GPU isn't being used or renders fail/black frames:** Switch to **CPU** mode in the GUI or run `run_cpu.bat`. It is slower on CPU, but avoids driver/ANGLE WebGL issues.
- **High RAM usage or browser workers crashing:** Lower the **Workers** count in the GUI (note that `run_loop.py` on the CLI defaults `--procs` to all logical CPU cores; for tight memory, use the GUI or run `tools/render/render.py` directly with a smaller `--procs` value).
- **`missing frames` error when encoding:** Run the render step again until all frames (`0` to `total_frames - 1`) are present in `final_v1/`.
- **Avoid running two renders at once:** Worker servers bind to sequential local ports starting at `8840`, so run only one film render at a time.
