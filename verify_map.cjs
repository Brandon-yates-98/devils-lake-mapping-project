const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const supabaseCalls = [];
  const consoleErrors = [];
  page.on('request', req => {
    if (req.url().includes('supabase.co')) supabaseCalls.push(req.url());
  });
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  await page.goto('http://localhost:8742/index.html');
  await page.waitForTimeout(6000);
  const badgeText = await page.textContent('#trail-count-badge').catch(() => 'not found');
  await page.screenshot({ path: 'verify_map.png' });
  console.log(JSON.stringify({ badgeText, supabaseCalls, consoleErrors }, null, 2));
  await browser.close();
})();
