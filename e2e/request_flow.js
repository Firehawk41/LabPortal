// Browser run-through of the demo flow. Needs a running portal seeded with the OSS demo data
// (scripts/seed_demo.py) plus users lab@example.com (staff, JM) and a@demo.example (customer 1),
// password demo-password-123. Run: NODE_PATH=$(npm root -g) node e2e/request_flow.js [shots-dir]
// Customer enters 10 samples: sets up row 1, pastes 9 IDs, adds one analysis to row 10 only, uses Ctrl+D.
const { chromium } = require('playwright');
const SHOTS = process.argv[2] || 'screenshots';
require('fs').mkdirSync(SHOTS, { recursive: true });
const BASE = process.env.PORTAL_URL || 'http://127.0.0.1:8000';
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await ctx.newPage();
  const errors = []; page.on('pageerror', e => errors.push(String(e)));
  await page.goto(`${BASE}/login`); await page.fill('#email', 'a@demo.example'); await page.fill('#password', 'demo-password-123'); await page.click('button[type=submit]');
  await page.goto(`${BASE}/requests/new`); await page.waitForSelector('#request_type-1');
  await page.check('#request_type-1');
  // set up sample 1
  const row1 = page.locator('#samples tr').first();
  await row1.locator(':is(input,select)[data-f=sample_name]').fill('BATCH-01');
  await row1.locator(':is(input,select)[data-f=chemical_id]').selectOption({ label: 'Chemical 01' });
  await row1.locator(':is(input,select)[data-f=processing_time]').selectOption({ label: 'Three Days' });
  await page.getByLabel('36 Elements', { exact: true }).check();
  await page.getByLabel('pH', { exact: true }).check();
  // paste 9 more IDs as a column copied from Excel
  await page.fill('#paste-ids', ['BATCH-02','BATCH-03','BATCH-04','BATCH-05','BATCH-06','BATCH-07','BATCH-08','BATCH-09','BATCH-10'].join('\n'));
  await page.click('#add-pasted');
  console.log('rows:', await page.locator('#samples tr').count());
  // change one sample: deselect all, select row 10, add TOC? (Chemical) -> add 4 Anions to row 10 only
  await page.locator('#samples tr').nth(9).locator('.analysis-chip').click();   // edit sample 10 alone
  await page.getByLabel('4 Anions', { exact: true }).check();
  await page.check('input[name=analysis_mode][value=all]');
  console.log('4 Anions state (all selected):', await page.getByLabel('4 Anions', { exact: true }).evaluate(b => b.indeterminate ? 'mixed' : b.checked));
  // Ctrl+D: row 3 notes
  await page.locator('#samples tr').nth(1).locator(':is(input,select)[data-f=additional_notes]').fill('keep cold');
  const n3 = page.locator('#samples tr').nth(2).locator(':is(input,select)[data-f=additional_notes]');
  await n3.focus(); await page.keyboard.press('Control+d');
  console.log('row3 notes after Ctrl+D:', await n3.inputValue());
  await page.locator('#samples-section').screenshot({ path: `${SHOTS}/10_sample_table.png` });
  await page.click('#submit-button'); await page.waitForURL(/\/requests\/TR\d+/);
  console.log('submitted', page.url());
  await page.screenshot({ path: `${SHOTS}/11_detail_10_samples.png`, fullPage: true });
  console.log('JS errors:', errors.length ? errors : 'none');
  await browser.close();
})().catch(e => { console.error('E2E FAILED:', e.message); process.exit(1); });
