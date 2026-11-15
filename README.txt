# Skies PC Render

Local GPU/CPU frame renderer, live monitor GUI, and MP4 encoder for Skies WebGL films.

This repo is the **renderer**. It does not make the film — an AI makes the film for you, using the Skies skill. You give the AI the skill and a prompt (below), it gives you a small film folder, you drop that folder in here, and this repo renders it on your GPU.

---

## ⚠️ First: you need the Skies skill

This renderer cannot create a film on its own. A film can only be made by an AI that has the **skies-cartoon-shorts skill**.

The skill is made and owned by **skies**. It is free to use, not for sale. Get it here: [skies Discord](https://discord.gg/MM8TPjcvN)

- Do **not** put the skill files in this repo, and do not share or sell the skill.
- Every video made with it must show the name **"skies"** painted into the scenery **2–3 times, no more, no fewer**, in different sets, each readable in at least one shot. Never remove, hide, blur, crop, rename, or cover it. That is the condition for using the skill for free.
- If you do not have the skill yet, get it from skies first: https://discord.gg/MM8TPjcvN — that's where the skill comes from. Without it, the prompt in this README will not work.

---

## Requirements

This bundle already includes `tools/render/node_modules` and configuration files. On your machine, you need:

- **Python 3.12+** (`python` / `pythonw` on Windows, `python3` on Linux/macOS) — tick "Add Python to PATH" during install
- **Node.js 20+**
- **Google Chrome, Microsoft Edge, or Playwright Chromium** (used headless for WebGL rendering and `--app` mode for the GUI)
- **FFmpeg & FFprobe** (`ffmpeg` and `ffprobe` on `PATH` for MP4 encoding and NVENC detection)
- **A GPU** (NVIDIA, AMD, or Intel Arc / Iris Xe) with up-to-date drivers, for GPU mode. CPU mode works without one, just slower.

---

## How a new film is made

1. **You pick a topic** and send the AI the skill + the prompt below.
2. **The AI writes a script** (140–170 words, loop ending), you approve it.
3. **You make the voiceover yourself** — any text-to-speech app (ElevenLabs, CapCut, etc.) or your own voice, reading the approved script word for word — and send the audio file to the AI.
4. **The AI builds the film** to your voiceover's timing, sends you check pictures, and you say "go" or tell it what to fix.
5. **The AI gives you a film pack folder** — a small folder, about 10–20 MB, named `films/<your-film>/`. That is the only thing you need to import.
6. **You render it here** (GUI or command line below), then encode the MP4.

One film at a time. Never run two renders at once.

---

## The prompt: give this to your AI

Copy everything in the box below and paste it into a chat with Muse, Claude, or any other AI — **after** you have uploaded the `skies-cartoon-shorts` skill to that chat. Replace the topic in the first line with yours.

```text
I have the skies-cartoon-shorts skill uploaded to this chat. Use it to make me a new Skies cartoon short.

Topic: Before calculators: "computer" was a job title, and rooms of people did the math by hand.

Follow the skill exactly, with these changes for a PC render:

1. SKILL FIRST. Read the skill's SKILL.md and LICENSE.md before you do anything.
   The skies mark is non-negotiable: the name "skies" must appear painted
   into the scenery 2-3 times, no more, no fewer, in different sets, each
   readable in at least one shot. Never remove, hide, blur, crop, rename,
   or cover it.

2. SCRIPT. Check every fact with a web search first and cite your sources.
   Write a script of 140-170 words, short sentences, one idea per sentence.
   Line 1 is the hook and must make sense on its own. Include one twist
   or question beat. The last line must loop straight back into line 1.
   Send me the script and wait for my approval before you do anything else.

3. VOICEOVER. I will make the voiceover myself and send you the audio
   file. Never generate the voice yourself. When it arrives, clean it and
   align it to the script exactly as the skill says (clean.py, align.py),
   and rebuild the film to my voiceover's timing. If my audio changes any
   words, tell me and update script.txt. TOTAL frames =
   round((clean length + 0.25 s) x 30).

4. CHECK PICTURES. Build the film in the skill's engine (story.ts PLAN/CAMS,
   acting.ts TRACKS, cast.ts, world.ts sets). Render check pictures of the
   mid-frame of every shot plus key moments, look at them yourself first,
   fix any framing / contact / label problems, then send me a contact-sheet
   JPG. Do NOT start a final render until I say "go".

5. SOUND, MUSIC, CAPTIONS. Follow the skill's Step 5 exactly:
   sound effects + voice at about -14 LUFS, original synthesized music
   ducked under the voice, and captions built from the script and the
   word timings. The final audio must be one file: audio/mix.wav.

6. DELIVER A FILM PACK, NOT A VIDEO. Do not render the final video yourself
   and do not send me an MP4. Instead, give me a folder I can import into
   my PC renderer (https://github.com/QuantumTan/skies-pc-render).
   The folder must be exactly this layout, named films/<slug>/ :

   films/<slug>/
     film.json          {"name": "<slug>", "title": "<Title>", "total_frames": <TOTAL>, "output": "<Title>_1080p.mp4"}
     engine/web/        built WebGL scene: index.html + app.js + assets (run esbuild as the skill says)
     audio/mix.wav      final mixed audio, about -14 LUFS
     caps/              caption PNGs + list.txt (from the skill's build.py)
     final_v1/          empty folder (this is where my PC will put rendered frames)

   Zip just that films/<slug>/ folder and send it to me. It should be
   about 10-20 MB. Do not include the tools/, the skill, or node_modules.

7. PC RENDER SETTINGS. The film must render with these settings, which
   my PC renderer uses:
   render.py --web engine/web --out final_v1 --range 0-<TOTAL-1> --w 540 --procs 2 --ms 1 --sm 2048
   then encode.py final_v1 <TOTAL> audio/mix.wav caps <Title>_1080p.mp4
   So keep --w 540, --ms 1, --sm 2048 in mind when you build the scenes.
   Do not change the render settings in your answer.

8. QUALITY CHECK BEFORE YOU SEND THE PACK. Confirm in your message:
   - length = TOTAL / 30 seconds
   - audio about -14 LUFS
   - captions present for every word
   - frame 0 and the last frame make a clean loop
   - no red skies-warning
   - the skies mark is readable 2-3 times, in different sets

Start with the script. Do not build anything until I approve it.
```

### What to send the AI, in order

- The skill file (`skies-cartoon-shorts.zip`) — first, before the prompt.
- The prompt above, with your topic in the first line.
- After it sends the script: your approval (or your edits).
- After it asks for the voice: your voiceover audio file (mp3, m4a, or wav).
- After it sends check pictures: "go", or what to fix.

---

## Importing a film pack

Unzip the pack the AI sent you, and drop the `films/<slug>/` folder into the `films/` folder in this repo:

```
films/
  knocker-upper/        # film 1, already in here
  human-computers/      # film 2, dropped in from a pack
```

It will appear automatically in the GUI film selector, or you can pass `<slug>` to `render.bat` / `encode.bat`.

---

## Option 1: Using the Desktop GUI (Recommended)

Double-click **`launch_gui.bat`** (or run `python gui.py` from a terminal).

1. **Select a Film**: Choose a film from the top-left dropdown (auto-discovered from `films/`), or click **Add folder** to select any film folder containing `film.json` and `engine/web/`.
2. **Choose Render Device**: Toggle **GPU** (hardware WebGL via ANGLE Direct3D 11) or **CPU** (software WebGL via SwiftShader) in the top-right.
3. **Test First (Optional)**: Expand **Render settings & test** and click **Test 5 frames (GPU)** to render 5 sample frames into `<film>/test_gpu/` and verify your GPU works properly.
4. **Adjust Workers & Quality (Optional)**:
   - **Workers**: Auto-recommended based on your CPU cores, RAM, and GPU VRAM. Lower this if you experience high memory usage or crashes. For GPU, 2 workers is a safe start.
   - **Render settings & test**: Configure render **Width** (`540`, `720`, or `1080` px in 9:16 portrait), **MSAA** (`1x`, `2x`, `4x`), and **Shadow map** (`1024`, `2048`, `4096`).
5. **Render Frames**: Click **Start Render**.
   - Shows live latest-frame preview, frame count, FPS, and ETA.
   - Click **Stop Safely** at any time — completed frames are preserved in `<film>/final_v1/` and skipped automatically when you resume.
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

  ```
  render.bat human-computers
  ```

- **Linux / macOS:**

  ```
  ./render.sh human-computers
  ```

- **Direct Python:**

  ```
  python run_loop.py films/human-computers
  ```

`run_loop.py` automatically runs `tools/render/render.py`, rescues completed frames from worker subfolders (`_w0`, `_w1`, ...) into `final_v1/`, and skips already-rendered `f_NNNNN.png` files. You can stop (`Ctrl+C`) and restart at any time without losing progress.

### Step 3 — Encode the Final MP4

Once all frames (`0` to `total_frames - 1`) are in `final_v1/`:

- **Windows:** Double-click **`encode.bat`** (or run `encode.bat <film-name>`).
- **Linux / macOS:**

  ```
  ./encode.sh human-computers
  ```

- **Direct Python:**

  ```
  python encode_film.py films/human-computers
  ```

- **Direct Encoder with NVENC (GPU H.264):**

  ```
  python tools/render/encode.py films/knocker-upper/final_v1 1129 films/knocker-upper/audio/mix.wav films/knocker-upper/caps films/knocker-upper/Before-Alarm-Clocks-Knocker-Upper_1080p.mp4 --nvenc
  ```

The encoder upscales frames to `1080x1920` (Lanczos) at `30 fps`, overlays captions from `caps/list.txt`, muxes `audio/mix.wav` (padded/trimmed to `total_frames / 30` seconds), and outputs H.264 (`libx264` CRF 17 or `h264_nvenc` CQ 18) + AAC `256k` audio.

---

## Project Structure

```
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

- **Test stuck at 0/5, browser never launches:** the Playwright headless shell is probably missing. This repo's `run.js` uses `channel: 'chromium'` so it uses the full Chromium already on your PC instead of the headless shell — make sure your `run.js` / `run.js.gpu` has that line. If you installed Chromium with `npx playwright install chromium` and it still fails, run the install from inside `tools/render` with the local CLI:
  `node node_modules\playwright-core\cli.js install chromium-headless-shell --force`
  If that download keeps failing with `ECONNRESET`, do not keep retrying it — the `channel: 'chromium'` fix above is the workaround.
- **GPU isn't being used or renders fail / black frames:** Switch to **CPU** mode in the GUI or run `run_cpu.bat`. It is slower on CPU (98% CPU is normal then), but avoids driver/ANGLE WebGL issues. Check Task Manager → Performance → GPU while a GPU test runs — the GPU graph should move, CPU should stay low.
- **Full render stuck at 0, but the 5-frame test works:** the full render launches a worker per CPU core, and too many Chromium instances fighting for one GPU can hang. Use the GUI and set Workers to 2, or run `tools/render/render.py` directly with `--procs 2`.
- **High RAM usage or browser workers crashing:** Lower the **Workers** count in the GUI (note that `run_loop.py` on the CLI defaults `--procs` to all logical CPU cores; for tight memory, use the GUI or run `tools/render/render.py` directly with a smaller `--procs` value).
- **`missing frames` error when encoding:** Run the render step again until all frames (`0` to `total_frames - 1`) are present in `final_v1/`.
- **Frames lost after stopping a render:** Frames are only safe once they are in `final_v1/` itself. Worker frames in `final_v1/_w0/` and `_w1/` are wiped when the next render starts, so `run_loop.py` moves them into `final_v1/` after every run. Do not delete `_w0` / `_w1` by hand while a render is running.
- **Avoid running two renders at once:** Worker servers bind to sequential local ports starting at `8840`, so run only one film render at a time.

---

## Credits

- Film skill: **skies** — `skies-cartoon-shorts`. Free to use, not for sale. Get it from the skies Discord: https://discord.gg/MM8TPjcvN — The "skies" mark must stay in every video made with it (see above).
- Renderer: this repo, built around the skill's engine and render tools.
