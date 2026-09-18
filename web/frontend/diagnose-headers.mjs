import { chromium } from 'playwright';

const BASE = 'http://localhost';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Intercept requests to see headers
  page.on('request', (req) => {
    const url = req.url();
    if (url.includes('/api/')) {
      const headers = req.headers();
      console.log(`REQUEST: ${req.method()} ${url}`);
      console.log(`  Authorization: ${headers.authorization || '(none)'}`);
    }
  });

  page.on('response', (resp) => {
    const url = resp.url();
    if (url.includes('/api/')) {
      console.log(`RESPONSE: ${resp.status()} ${url}`);
    }
  });

  // Go to login
  console.log('=== Navigating to login ===');
  await page.goto(BASE);
  await page.waitForLoadState('networkidle');

  // Log in
  console.log('\n=== Logging in ===');
  await page.fill('input[type="text"]', 'student01');
  await page.fill('input[type="password"]', 'student123');
  await page.click('button[type="submit"]');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  console.log('\n=== After login, checking localStorage ===');
  const token = await page.evaluate(() => localStorage.getItem('pseint:token'));
  console.log('Token in localStorage:', token ? token.substring(0, 20) + '...' : 'null');

  console.log('\n=== Reloading page to simulate fresh visit ===');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);

  console.log('\n=== Navigating to /practice ===');
  await page.goto(BASE + '/practice');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);

  await browser.close();
})();
