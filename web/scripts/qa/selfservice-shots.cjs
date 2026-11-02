const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const server = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3197'], { cwd: path.resolve('web'), stdio: ['ignore', 'pipe', 'pipe'] });
  const log = fs.createWriteStream('validation/next-start.log');
  server.stdout.pipe(log); server.stderr.pipe(log);
  let browser;
  try {
    for (let attempt = 0; attempt < 90; attempt++) {
      try { const res = await fetch('http://127.0.0.1:3197/local/cloud'); if (res.ok) break; } catch {}
      await new Promise(r => setTimeout(r, 1000));
    }
    browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    fs.mkdirSync('shots', { recursive: true });
    const checks = [];
    for (const width of [1440, 390]) {
      const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1000 }, colorScheme: 'light' });
      const failures = [];
      page.on('pageerror', err => failures.push(String(err)));
      // A direct next start needs the hub's /local/_next asset-prefix mapping.
      await page.route('**/local/_next/**', route => route.continue({ url: route.request().url().replace('/local/_next/', '/_next/') }));
      for (const [name, url] of [['mammoth-local', '/models/mammoth-1/local'], ['cloud', '/local/cloud'], ['hardware-requested', '/hardware?model=mammoth-1&requested=1']]) {
        const response = await page.goto(`http://127.0.0.1:3197${url}`, { waitUntil: 'networkidle' });
        await page.evaluate(() => document.fonts.ready);
        await page.locator('img').evaluateAll(async items => {
          for (const item of items) item.loading = 'eager';
          await Promise.all(items.map(item => item.decode().catch(() => {})));
        });
        const images = await page.locator('img').evaluateAll(items => items.map(i => ({ src: i.getAttribute('src'), loaded: i.complete && i.naturalWidth > 0 })));
        const overflow = await page.evaluate(() => ({ viewport: innerWidth, scroll: document.documentElement.scrollWidth }));
        await page.screenshot({ path: `shots/${name}-${width}.png`, fullPage: true });
        checks.push({ name, width, status: response.status(), overflow, images, pageErrors: [...failures] });
      }
      await page.close();
    }
    fs.writeFileSync('validation/screenshots.json', JSON.stringify(checks, null, 2));
    if (checks.some(c => c.status !== 200 || c.overflow.scroll > c.overflow.viewport || c.images.some(i => !i.loaded) || c.pageErrors.length)) process.exitCode = 1;
    console.log(JSON.stringify(checks.map(({ name, width, status, overflow, pageErrors }) => ({ name, width, status, overflow, pageErrors })), null, 2));
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
    await new Promise(resolve => server.once('exit', resolve));
    log.end();
  }
})().catch(err => { console.error(err); process.exitCode = 1; });
