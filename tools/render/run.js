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
  p.on('pageerror', e => console.log('PAGEERR', String(e).slice(0, 400)));
  p.on('console', msg => {
    if (msg.type() === 'error') console.log('CONSOLE_ERR', msg.text().slice(0, 400));
  });

  const url = `http://127.0.0.1:${port}/index.html?w=${w || 1080}&ms=${ms}&sm=${sm}&list=${list}`;
  try {
    await p.goto(url, { timeout: 120000, waitUntil: 'domcontentloaded' });
  } catch (err) {
    console.log('PAGE_GOTO_ERR', err.message);
  }

  const t0 = Date.now();
  const doneFile = path.join(out, 'DONE');
  while (b.isConnected() && !fs.existsSync(doneFile) && Date.now() - t0 < 6 * 3600e3) {
    await new Promise(r => setTimeout(r, 1000));
  }
  try { await b.close(); } catch (_) {}
  process.exit(0);
})();
