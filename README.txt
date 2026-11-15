SKIES RENDER - FINAL - RTX 3050 GPU
=====================================
This is the final folder. No more edits, no more downloads.
Unzip it, test once, then render. It already has 347 frames done.

WHAT'S FIXED IN THIS VERSION
- GPU is forced: DirectX 11 on your RTX 3050, not SwiftShader CPU.
  tools/render/run.js uses channel: 'chromium' + --use-angle=d3d11,
  so it uses the full Chromium already on your PC. It does NOT need
  the headless-shell download that kept failing.
- CPU fallback (run_cpu.bat) is fixed the same way.
- run_loop.py now saves worker frames after every run, so stopping
  and restarting never loses frames.

YOU ALREADY HAVE EVERYTHING INSTALLED
Python, Node.js, ffmpeg, Chromium - all done. Do not install anything else.

STEP 1 - TEST THE GPU (2-3 minutes)
Double-click test_gpu.bat. It renders 5 frames.
Watch Task Manager > Performance > GPU - your RTX 3050 should move,
and CPU should stay low. The 5 test frames land in:
  films\knocker-upper\final_v1\_w0\
They should look the same as the CPU frames already in final_v1.

STEP 2 - RENDER THE REST
Double-click render.bat (or run_gpu.bat - same thing).
It starts at frame 348 and runs to 1,129. Leave it running.
It is safe to stop (Ctrl+C) and start it again - it skips frames done.
Do NOT run two films at once.

IMPORTANT: tell Muse when you start the PC render, so the cloud
render can be stopped - otherwise both machines do the same work.

STEP 3 - MAKE THE MP4
When it says ALL FRAMES DONE, double-click encode.bat.
That makes Before-Alarm-Clocks-Knocker-Upper_1080p.mp4 in
films\knocker-upper\. Send that MP4 back to Muse here.

IF GPU STILL DOESN'T MOVE
Double-click run_cpu.bat instead. It will be slower (CPU 98% is
normal then), but it works. Tell Muse - the cloud render is still
going as a backup, at 347 frames and finishing around 11pm tonight.
