import { chromium } from 'playwright';

const BASE = 'http://localhost';
const TABS = [
  { path: '/', label: 'Home' },
  { path: '/practice', label: 'Practice' },
  { path: '/forum', label: 'Forum' },
  { path: '/contests', label: 'Contests' },
  { path: '/submissions', label: 'Submissions' },
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Collectors
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push({ url: page.url(), text: msg.text() });
  });
  page.on('pageerror', (err) => pageErrors.push({ url: page.url(), error: err.message }));
  page.on('response', (resp) => {
    if (resp.status() >= 400) {
      failedRequests.push({ url: page.url(), status: resp.status(), reqUrl: resp.url() });
    }
  });

  // 1. Go to login page
  console.log('=== Navigating to login ===');
  await page.goto(BASE);
  await page.waitForLoadState('networkidle');
  console.log('URL:', page.url());

  // 2. Log in
  console.log('\n=== Logging in as student01 ===');
  try {
    await page.fill('input[name="username"], input[placeholder*="usuario"], input[type="text"]', 'student01');
    await page.fill('input[name="password"], input[type="password"]', 'student123');
    await page.click('button[type="submit"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    console.log('After login URL:', page.url());
  } catch (e) {
    console.log('Login error:', e.message);
  }

  // 3. Visit each tab
  for (const tab of TABS) {
    console.log(`\n=== Tab: ${tab.label} (${tab.path}) ===`);
    const tabConsoleErrors = [];
    const tabPageErrors = [];
    const tabFailedReqs = [];

    // Reset collectors for this tab
    consoleErrors.length = 0;
    pageErrors.length = 0;
    failedRequests.length = 0;

    try {
      await page.goto(BASE + tab.path, { waitUntil: 'networkidle', timeout: 10000 });
      await page.waitForTimeout(2000);

      const url = page.url();
      const bodyText = await page.textContent('body');
      const heading = await page.$eval('h1, h2, [role="heading"]', el => el.textContent).catch(() => '(no heading)');

      console.log('URL:', url);
      console.log('Heading:', heading);

      // Check for specific states
      if (bodyText.includes('Cargando')) console.log('STATE: Shows "Cargando..."');
      if (bodyText.includes('No se pudieron cargar')) console.log('STATE: Shows "No se pudieron cargar..."');
      if (bodyText.includes('Algo salió mal')) console.log('STATE: Shows ErrorBoundary "Algo salió mal..."');
      if (bodyText.includes('Error')) console.log('STATE: Contains "Error"');

      // Show first 300 chars of body text for context
      const snippet = bodyText.replace(/\s+/g, ' ').trim().substring(0, 400);
      console.log('Body snippet:', snippet);

      // Report collected errors for this tab
      if (consoleErrors.length) console.log('Console errors:', JSON.stringify(consoleErrors, null, 2));
      if (pageErrors.length) console.log('Page errors:', JSON.stringify(pageErrors, null, 2));
      if (failedRequests.length) console.log('Failed requests:', JSON.stringify(failedRequests, null, 2));

      if (!consoleErrors.length && !pageErrors.length && !failedRequests.length) {
        console.log('No errors detected on this tab.');
      }
    } catch (e) {
      console.log('Navigation error:', e.message);
    }
  }

  await browser.close();
  console.log('\n=== Done ===');
})();
