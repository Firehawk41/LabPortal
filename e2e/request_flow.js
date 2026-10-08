const { chromium } = require('playwright');
// Browser run-through of the demo flow. Needs a running portal seeded with the OSS demo data
// (scripts/seed_demo.py) plus users lab@example.com (staff, JM) and a@demo.example (customer 1),
// password demo-password-123. Run: NODE_PATH=$(npm root -g) node e2e/request_flow.js [shots-dir]
const SHOTS = process.argv[2] || 'screenshots';
require('fs').mkdirSync(SHOTS, { recursive: true });
const BASE = process.env.PORTAL_URL || 'http://127.0.0.1:8000';
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  const shot = (n) => page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: true });
  async function login(email) {
    await page.goto(`${BASE}/login`);
    await page.fill('#email', email); await page.fill('#password', 'demo-password-123');
    await page.click('button[type=submit]');
  }
  // customer
  await login('a@demo.example');
  await page.goto(`${BASE}/requests/new`);
  await page.waitForSelector('#request_type-1');
  await page.check('#request_type-1');
  await page.fill('#customer_contact', 'Jane Doe'); await page.fill('#customer_phone', '555-1234');
  await page.fill('#results_to', 'jane@a.example');
  await page.fill('#po_number', 'PO-1');
  const card = page.locator('.sample-card').first();
  await card.locator('[data-f=sample_name]').fill('S-001');
  await card.locator('[data-f=chemical_id]').selectOption({ label: 'Chemical 01' });
  await card.locator('[data-f=processing_time]').selectOption({ label: 'Next Day Time Limited' });
  await card.locator('[data-f=requested_time]').fill('15:00');
  await card.getByLabel('36 Elements', { exact: true }).check();
  await card.getByLabel('pH', { exact: true }).check();
  await card.locator('[data-f=additional_element_ids]').fill('Fe, Li');
  await card.locator('[data-action=copy]').click();
  await page.locator('.sample-card').nth(1).locator('[data-f=sample_name]').fill('S-002');
  await shot('01_form_filled');
  await page.locator('.sample-card').nth(1).getByLabel('pH', { exact: true }).uncheck(); await page.locator('.sample-card').nth(1).getByLabel('36 Elements', { exact: true }).uncheck();
  await page.click('#submit-button');           // invoice_to missing + sample 2 no analyses -> 422
  await page.waitForSelector('#form-error:not(.hidden)');
  console.log('ERRORS SHOWN:', (await page.textContent('#form-error')).replace(/\s+/g, ' '));
  await shot('02_form_errors');
  await page.fill('#invoice_to', 'ap@a.example');
  await page.click('#submit-button');
  await page.waitForURL(/\/requests\/TR\d+/);
  console.log('SUBMITTED ->', page.url());
  await shot('03_detail_customer');
  // wafer request, prefilled contact from the last request
  await page.goto(`${BASE}/requests/new`);
  await page.waitForSelector('#request_type-3');
  console.log('PREFILL contact:', await page.inputValue('#customer_contact'), '| invoice:', await page.inputValue('#invoice_to'));
  await page.check('#request_type-3');
  const w = page.locator('.sample-card').first();
  await w.locator('[data-f=sample_name]').fill('Lot 7');
  await w.locator('[data-f=wafer_size]').selectOption({ label: '300 mm' });
  await w.locator('[data-f=reporting_unit]').selectOption({ index: 2 });
  await w.locator('[data-f=processing_time]').selectOption({ label: 'Next Day RUSH' });
  await w.getByLabel('36 Elements', { exact: true }).check();
  console.log('WAFER chemical hidden:', await w.locator('[data-only="1"]').isHidden(), '| wafer analyses:', await w.locator('.analyses input').count());
  await shot('04_wafer_form');
  await page.click('#submit-button');
  await page.waitForURL(/\/requests\/TR\d+/);
  await page.goto(`${BASE}/`);
  await shot('05_customer_list');
  await page.click('button.nav-link-button');
  // staff
  await login('lab@example.com');
  await shot('06_staff_home');
  await page.goto(`${BASE}/requests/TR00001`);
  await page.click('text=Mark received');
  await page.waitForSelector('.flash');
  console.log('FLASH:', await page.textContent('.flash'));
  await shot('07_staff_received');
  await page.goto(`${BASE}/requests/new`);
  await page.waitForSelector('#customer_id option:nth-child(3)', { state: 'attached' });
  await shot('08_staff_new_form');
  console.log('JS ERRORS:', errors.length ? errors : 'none');
  await browser.close();
})().catch(e => { console.error('E2E FAILED:', e.message); process.exit(1); });
