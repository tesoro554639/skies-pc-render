// one headless Chromium (HARDWARE GPU WebGL) rendering a list of frames: node run.js PORT "f1,f2,..." OUTDIR WIDTH [MSAA] [SHADOWMAP]
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function launchBrowser(args) {
  for (const opts of [
    { channel: 'chrome', args },
    { channel: 'msedge', args },
    { channel: 'chromium', args },
    { args },
  ]) {
    try { return await chromium.launch(opts); } catch (_) {}
  }
  throw new Error('No Chrome, Edge, or Playwright Chromium executable found.');
}

(async () => {
  const [port, list, out, w] = process.argv.slice(2);
  const ms = process.argv[6] || 4;
  const sm = process.argv[7] || 4096;

  const isWin = process.platform === 'win32';
  const isMac = process.platform === 'darwin';
  const angleBackend = isWin ? 'd3d11' : (isMac ? 'metal' : 'vulkan');
  const gpuArgs = [
    '--use-gl=angle',
    `--use-angle=${angleBackend}`,
    '--force_high_performance_gpu',
    '--ignore-gpu-blocklist',
    '--disable-gpu-sandbox',
  ];

  let b;
  try {
    b = await launchBrowser(gpuArgs);
  } catch (err) {
    console.log('BROWSER_LAUNCH_ERR', err.message);
    process.exit(1);
  }

  const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  let lastFatalError = null;
  p.on('pageerror', e => {
    lastFatalError = String(e);
    console.log('PAGEERR', lastFatalError.slice(0, 400));
  });
  p.on('console', msg => {
    if (msg.type() === 'error') console.log('CONSOLE_ERR', msg.text().slice(0, 400));
  });

  await p.addInitScript(() => {
    if (typeof window.kickAt === 'undefined') {
      const recoil = [[11.43, 0.6], [26.14, 0.45], [45.09, 0.5]];
      window.kickAt = function(t) {
        let e = 0;
        for (let [n, r] of recoil) {
          let i = Math.floor((t - n) * 30 + 1e-6);
          if (i >= 0 && i < 7) e += r * (i % 2 ? -1 : 1) * Math.pow(1 - i / 7, 1.5);
        }
        return e;
      };
    }
  });

  const url = `http://127.0.0.1:${port}/index.html?w=${w || 1080}&ms=${ms}&sm=${sm}&list=${list}`;
  for (let attempt = 1; attempt <= 5; attempt++) {
    try {
      await p.goto(url, { timeout: 120000, waitUntil: 'domcontentloaded' });
      break;
    } catch (err) {
      if (attempt === 5) {
        console.log('PAGE_GOTO_ERR', err.message);
      } else {
        await new Promise(r => setTimeout(r, 1000));
      }
    }
  }

  const t0 = Date.now();
  const doneFile = path.join(out, 'DONE');
  let lastFrameTime = Date.now();
  let lastFrameCount = 0;

  while (b.isConnected() && !fs.existsSync(doneFile) && Date.now() - t0 < 6 * 3600e3) {
    await new Promise(r => setTimeout(r, 1000));
    let currentFrames = 0;
    try {
      currentFrames = fs.readdirSync(out).filter(f => f.endsWith('.png')).length;
    } catch (_) {}

    if (currentFrames > lastFrameCount) {
      lastFrameCount = currentFrames;
      lastFrameTime = Date.now();
    } else {
      if (lastFatalError && Date.now() - lastFrameTime > 10000) {
        console.log('FATAL_ABORT_AFTER_PAGEERR', lastFatalError.slice(0, 300));
        break;
      }
      if (Date.now() - lastFrameTime > 90000) {
        console.log('STALL_TIMEOUT_EXCEEDED (no progress for 90s)');
        break;
      }
    }
  }
  try { await b.close(); } catch (_) {}
  process.exit(lastFatalError ? 1 : 0);
})();
