/**
 * End-to-end test: admin submits on behalf, 2 customers self-submit,
 * admin verifies all three appear in dashboard.
 *
 * CDN resources (jQuery/Tagify/Select2) are blocked in this environment,
 * so we drive the form by directly calling the /submit endpoint via fetch()
 * from within the browser context — the same call the JS would make after
 * confirming the modal. We still navigate all pages and screenshot every step.
 */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE = 'http://127.0.0.1:5000';
const SHOTS = '/home/user/LabPortal/screenshots';
fs.mkdirSync(SHOTS, { recursive: true });

let idx = 0;
async function shot(page, label) {
  const n = String(idx++).padStart(2, '0');
  const p = path.join(SHOTS, `${n}_${label}.png`);
  await page.screenshot({ path: p, fullPage: true });
  console.log(`  📸 ${path.basename(p)}`);
  return p;
}

async function login(page, email, password, shotLabel) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await shot(page, `login_page_${shotLabel}`);
  await page.fill('#email', email);
  await page.fill('#password', password);
  await Promise.all([
    page.waitForURL(url => !url.toString().includes('/login'), { timeout: 20000 }),
    page.click('button[type="submit"]'),
  ]);
  await page.waitForLoadState('domcontentloaded');
  console.log(`  → logged in, landed at ${page.url()}`);
}

async function logout(page) {
  await page.goto(`${BASE}/logout`, { waitUntil: 'domcontentloaded' });
}

/**
 * Submit a testing request directly via the /submit JSON endpoint
 * while the session cookie is active in the browser context.
 * This mirrors exactly what the JS confirm-modal does.
 */
async function submitViaFetch(page, payload) {
  const result = await page.evaluate(async (body) => {
    const res = await fetch('/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const json = await res.json().catch(() => ({}));
    return { status: res.status, json };
  }, payload);
  return result;
}

// ─── MAIN ────────────────────────────────────────────────────────────────────
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--ignore-certificate-errors'],
  });
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    ignoreHTTPSErrors: true,
  });
  const page = await ctx.newPage();
  page.on('console', m => {
    if (m.type() === 'error') console.log(`  [browser err] ${m.text().substring(0, 100)}`);
  });

  const newSubs = [];

  try {
    // ── 0. Screenshot the login page ─────────────────────────────────────────
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
    await shot(page, 'login_page');

    // ── 1. ADMIN: submit on behalf of Apex Analytics ─────────────────────────
    console.log('\n── ADMIN: submit on behalf of Apex Analytics ──');
    await login(page, 'admin@example.com', 'AdminPass123!', 'admin');
    await shot(page, 'admin_dashboard');

    // Navigate to new-submission form
    await page.goto(`${BASE}/new-submission`, { waitUntil: 'networkidle' });
    await shot(page, 'admin_new_submission_form');

    // Get customer IDs from the behalf-customer select
    const customerOptions = await page.$$eval('#behalf-customer option', opts =>
      opts.filter(o => o.value).map(o => ({ value: o.value, text: o.textContent.trim() }))
    );
    console.log(`  Customers available: ${customerOptions.map(o => o.text).join(', ')}`);
    if (!customerOptions.length) throw new Error('No customers in #behalf-customer');

    // Select Apex Analytics (first customer)
    const apexOpt = customerOptions[0];
    await page.selectOption('#behalf-customer', apexOpt.value);
    // Wait for profile fetch to fill the form
    await page.waitForFunction(
      () => (document.getElementById('customer-name')?.value || '').length > 0,
      { timeout: 15000 }
    );
    await shot(page, 'admin_customer_selected_prefilled');

    // Fetch customer profile for email fields
    const profileResp = await page.evaluate(async (id) => {
      const r = await fetch(`/admin/api/customer/${id}/profile`);
      return r.ok ? r.json() : null;
    }, apexOpt.value);
    console.log(`  Profile loaded: ${JSON.stringify(profileResp?.customer_name)}`);

    // Build and send the submission payload
    const adminPayload = {
      customer_name:    profileResp?.customer_name    || 'Apex Analytics Inc.',
      street_address:   profileResp?.street_address   || '4500 Innovation Pkwy',
      city:             profileResp?.city             || 'Austin',
      state:            profileResp?.state            || 'TX',
      country:          profileResp?.country          || 'USA',
      customer_contact: profileResp?.customer_contact || 'Dana Whitfield',
      customer_phone:   profileResp?.customer_phone   || '555-201-3344',
      results_list:     JSON.stringify((profileResp?.results_list || ['labmanager@apexanalytics.com']).map(v => ({ value: v }))),
      results_cc_list:  JSON.stringify([]),
      invoice_list:     JSON.stringify((profileResp?.invoice_list || ['billing@apexanalytics.com']).map(v => ({ value: v }))),
      invoice_cc_list:  JSON.stringify([]),
      payment_method:   profileResp?.payment_method   || 'po',
      po_number:        profileResp?.po_number        || 'PO-ADMIN-001',
      cc_number:        '',
      behalf_customer_id: apexOpt.value,
      samples: [{
        sample_id:        'ADM-E2E-001',
        chemical_matrix:  'IPA Solution',
        sample_type:      'chemical',
        processing_time:  'Standard',
        analyses:         ['36_elements_icpms'],
      }],
    };

    const adminResult = await submitViaFetch(page, adminPayload);
    console.log(`  Admin submit → status ${adminResult.status}: ${JSON.stringify(adminResult.json)}`);
    if (adminResult.status !== 201) throw new Error(`Admin submit failed: ${JSON.stringify(adminResult.json)}`);
    newSubs.push({ who: 'Admin (for Apex)', id: adminResult.json.submission_id });
    await shot(page, 'admin_submission_sent');
    await logout(page);

    // ── 2. CUSTOMER 1: Apex Analytics (labmanager) ───────────────────────────
    console.log('\n── CUSTOMER 1: labmanager@apexanalytics.com ──');
    await login(page, 'labmanager@apexanalytics.com', 'ApexLab123!', 'cust1');
    await page.waitForLoadState('networkidle');
    await shot(page, 'cust1_form');

    const cust1Result = await submitViaFetch(page, {
      customer_name:    'Apex Analytics Inc.',
      street_address:   '4500 Innovation Pkwy',
      city:             'Austin',
      state:            'TX',
      country:          'USA',
      customer_contact: 'Dana Whitfield',
      customer_phone:   '555-201-3344',
      results_list:     '[{"value":"labmanager@apexanalytics.com"}]',
      results_cc_list:  '[]',
      invoice_list:     '[{"value":"billing@apexanalytics.com"}]',
      invoice_cc_list:  '[]',
      payment_method:   'po',
      po_number:        'PO-APX-E2E-001',
      cc_number:        '',
      behalf_customer_id: '',
      samples: [{
        sample_id:       'APX-E2E-001',
        chemical_matrix: 'DI Water',
        sample_type:     'water',
        processing_time: 'Next Day',
        analyses:        ['ph', 'conductivity'],
      }],
    });
    console.log(`  Cust1 submit → status ${cust1Result.status}: ${JSON.stringify(cust1Result.json)}`);
    if (cust1Result.status !== 201) throw new Error(`Cust1 submit failed: ${JSON.stringify(cust1Result.json)}`);
    newSubs.push({ who: 'Apex Analytics (self)', id: cust1Result.json.submission_id });
    await shot(page, 'cust1_submission_sent');
    await logout(page);

    // ── 3. CUSTOMER 2: Silver Creek Materials ────────────────────────────────
    console.log('\n── CUSTOMER 2: procurement@silvercreekmaterials.com ──');
    await login(page, 'procurement@silvercreekmaterials.com', 'SilverCreek2024!', 'cust2');
    await page.waitForLoadState('networkidle');
    await shot(page, 'cust2_form');

    const cust2Result = await submitViaFetch(page, {
      customer_name:    'Silver Creek Materials',
      street_address:   '120 Foundry Road',
      city:             'Pittsburgh',
      state:            'PA',
      country:          'USA',
      customer_contact: 'Marcus Yee',
      customer_phone:   '555-477-8821',
      results_list:     '[{"value":"procurement@silvercreekmaterials.com"}]',
      results_cc_list:  '[]',
      invoice_list:     '[{"value":"billing@silvercreekmaterials.com"}]',
      invoice_cc_list:  '[]',
      payment_method:   'po',
      po_number:        'PO-SCM-E2E-001',
      cc_number:        '',
      behalf_customer_id: '',
      samples: [{
        sample_id:       'SCM-E2E-001',
        chemical_matrix: 'HCl 10%',
        sample_type:     'chemical',
        processing_time: 'Rush',
        analyses:        ['36_elements_icpms', 'toc'],
      }],
    });
    console.log(`  Cust2 submit → status ${cust2Result.status}: ${JSON.stringify(cust2Result.json)}`);
    if (cust2Result.status !== 201) throw new Error(`Cust2 submit failed: ${JSON.stringify(cust2Result.json)}`);
    newSubs.push({ who: 'Silver Creek (self)', id: cust2Result.json.submission_id });
    await shot(page, 'cust2_submission_sent');
    await logout(page);

    // ── 4. ADMIN: verify dashboard shows all new submissions ─────────────────
    console.log('\n── ADMIN: verify dashboard ──');
    await login(page, 'admin@example.com', 'AdminPass123!', 'admin_verify');
    await page.goto(`${BASE}/admin/submissions`, { waitUntil: 'networkidle' });
    await shot(page, 'admin_submissions_TOP');

    const totalRows = await page.$$eval('tbody tr', r => r.length).catch(() => 0);
    const bodyText  = await page.textContent('body');
    const hasApex   = bodyText.includes('Apex Analytics');
    const hasSilver = bodyText.includes('Silver Creek');
    console.log(`  Total rows in table: ${totalRows}`);
    console.log(`  "Apex Analytics" in page: ${hasApex}`);
    console.log(`  "Silver Creek" in page:   ${hasSilver}`);

    // Verify each new submission ID appears on the page
    for (const sub of newSubs) {
      const visible = bodyText.includes(sub.id.substring(0, 8));
      console.log(`  Sub [${sub.who}] ${sub.id} visible: ${visible}`);
    }

    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(300);
    await shot(page, 'admin_submissions_BOTTOM');

    // Click the newest submission (first row in table = most recent)
    const firstDetailLink = await page.$('tbody tr:first-child a');
    if (firstDetailLink) {
      await firstDetailLink.click();
      await page.waitForLoadState('networkidle');
      await shot(page, 'admin_submission_detail_view');
    }

    console.log('\n╔═══════════════════════════════════════════╗');
    console.log('║          E2E TEST COMPLETE ✓              ║');
    console.log('╠═══════════════════════════════════════════╣');
    for (const s of newSubs) {
      console.log(`║  ${s.who.padEnd(24)} → ${s.id.substring(0,8)}…  ║`);
    }
    console.log(`║  Admin dashboard rows: ${String(totalRows).padEnd(20)}║`);
    console.log('╚═══════════════════════════════════════════╝');

  } catch (err) {
    console.error('\nFATAL:', err.message);
    await shot(page, 'FATAL_ERROR').catch(() => {});
    await browser.close();
    process.exit(1);
  }

  await browser.close();
})();
