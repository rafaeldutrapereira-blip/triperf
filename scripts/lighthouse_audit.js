/**
 * Lighthouse audit via Playwright CDP
 * Uses Playwright's bundled Chromium — no system Chrome needed.
 */
const { chromium } = require('playwright');
const lighthouse  = require('lighthouse');

const PAGES = [
  { name: 'login',       url: 'http://localhost:8000/login.html' },
  { name: 'registro',    url: 'http://localhost:8000/registro.html' },
];

const CATEGORIES = ['performance', 'accessibility', 'best-practices', 'seo'];

async function audit(page_info) {
  const browser = await chromium.launch({
    args: ['--remote-debugging-port=9222', '--no-sandbox'],
  });
  try {
    const ctx  = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto(page_info.url, { waitUntil: 'networkidle' });

    const { lhr } = await lighthouse(page_info.url, {
      port: 9222,
      output: 'json',
      logLevel: 'error',
      onlyCategories: CATEGORIES,
    });

    const scores = {};
    CATEGORIES.forEach(c => {
      scores[c] = Math.round((lhr.categories[c]?.score ?? 0) * 100);
    });

    console.log(`\n=== ${page_info.name} ===`);
    CATEGORIES.forEach(c => {
      const s = scores[c];
      const ok = s >= 80 ? '✅' : '❌';
      console.log(`  ${ok} ${c}: ${s}`);
    });

    return scores;
  } finally {
    await browser.close();
  }
}

(async () => {
  const results = {};
  for (const p of PAGES) {
    try {
      results[p.name] = await audit(p);
    } catch (e) {
      console.error(`ERROR auditing ${p.name}: ${e.message}`);
      results[p.name] = null;
    }
  }

  console.log('\n=== SUMMARY ===');
  let allPass = true;
  for (const [name, scores] of Object.entries(results)) {
    if (!scores) { console.log(`  ${name}: FAILED`); allPass = false; continue; }
    const min = Math.min(...Object.values(scores));
    const ok = min >= 80 ? '✅' : '❌';
    if (min < 80) allPass = false;
    console.log(`  ${ok} ${name}: min=${min}`);
  }
  process.exit(allPass ? 0 : 1);
})();
