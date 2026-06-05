const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE_URL = process.env.TOMODACHI_URL || 'http://127.0.0.1:8000/';
const OUT_DIR = path.join(__dirname, '..', 'screenshots');

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

async function waitForGame(page) {
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForSelector('#gameCanvas', { timeout: 10000 });
  await page.waitForFunction(() => {
    const canvas = document.querySelector('#gameCanvas');
    const cards = document.querySelectorAll('.agent-card');
    return canvas && canvas.width > 0 && canvas.height > 0 && cards.length > 0;
  }, { timeout: 15000 });
  await page.waitForTimeout(1800);
}

async function getCanvasStats(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('#gameCanvas');
    if (!canvas) return { exists: false };

    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const sampleW = Math.min(w, 240);
    const sampleH = Math.min(h, 180);
    const sx = Math.max(0, Math.floor((w - sampleW) / 2));
    const sy = Math.max(0, Math.floor((h - sampleH) / 2));
    const data = ctx.getImageData(sx, sy, sampleW, sampleH).data;

    const seen = new Set();
    let alphaPixels = 0;
    let nonBackgroundPixels = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      const a = data[i + 3];
      if (a > 0) alphaPixels++;
      if (!(r === 237 && g === 224 && b === 196)) nonBackgroundPixels++;
      if (seen.size < 400) seen.add(`${r},${g},${b},${a}`);
    }

    return {
      exists: true,
      width: w,
      height: h,
      uniqueColors: seen.size,
      alphaPixels,
      nonBackgroundPixels,
      agentCards: document.querySelectorAll('.agent-card').length,
      logEntries: document.querySelectorAll('.log-entry').length,
      statusText: document.querySelector('#status-bar')?.textContent || '',
      modelText: document.querySelector('#model-badge')?.textContent || '',
    };
  });
}

async function runViewport(browser, viewport) {
  const page = await browser.newPage({ viewport });
  const consoleMessages = [];
  const pageErrors = [];

  page.on('console', msg => {
    if (['error', 'warning'].includes(msg.type())) {
      consoleMessages.push(`${msg.type()}: ${msg.text()}`);
    }
  });
  page.on('pageerror', err => pageErrors.push(err.message));

  await waitForGame(page);
  const stats = await getCanvasStats(page);
  const screenshotPath = path.join(OUT_DIR, `${viewport.name}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await page.close();

  const canvasLooksDrawn =
    stats.exists &&
    stats.width > 0 &&
    stats.height > 0 &&
    stats.uniqueColors > 20 &&
    stats.nonBackgroundPixels > 1000;

  return {
    viewport: viewport.name,
    screenshot: screenshotPath,
    canvasLooksDrawn,
    stats,
    consoleMessages,
    pageErrors,
  };
}

async function main() {
  ensureDir(OUT_DIR);
  const browser = await chromium.launch({ headless: true });
  const results = [];

  try {
    for (const viewport of VIEWPORTS) {
      results.push(await runViewport(browser, viewport));
    }
  } finally {
    await browser.close();
  }

  const reportPath = path.join(OUT_DIR, 'visual_report.json');
  fs.writeFileSync(reportPath, JSON.stringify({
    url: BASE_URL,
    checkedAt: new Date().toISOString(),
    results,
  }, null, 2));

  for (const result of results) {
    console.log(`${result.viewport}: ${result.canvasLooksDrawn ? 'OK' : 'FAIL'}`);
    console.log(`  screenshot: ${result.screenshot}`);
    console.log(`  canvas: ${result.stats.width}x${result.stats.height}, colors=${result.stats.uniqueColors}, agents=${result.stats.agentCards}, status="${result.stats.statusText}"`);
    if (result.consoleMessages.length) console.log(`  console: ${result.consoleMessages.join(' | ')}`);
    if (result.pageErrors.length) console.log(`  errors: ${result.pageErrors.join(' | ')}`);
  }
  console.log(`report: ${reportPath}`);

  if (results.some(result => !result.canvasLooksDrawn || result.pageErrors.length)) {
    process.exitCode = 1;
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
