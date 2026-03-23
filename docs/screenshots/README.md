# Screenshots

These screenshots are taken with Puppeteer using the Claudius Banks test persona.

## How to regenerate

From the project root, with the backend running (`make dev`):

```bash
node -e "
const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  const dir = 'docs/screenshots';

  // Helper: resize viewport to capture full scrollable content
  async function fullPageScreenshot(page, path) {
    const height = await page.evaluate(() => {
      const main = document.querySelector('main');
      return main ? main.scrollHeight + 120 : document.body.scrollHeight;
    });
    await page.setViewport({ width: 1400, height: Math.max(900, height) });
    await new Promise(r => setTimeout(r, 500));
    await page.screenshot({ path });
    await page.setViewport({ width: 1400, height: 900 });
  }

  // Login as Claudius Banks
  await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle2' });
  await page.screenshot({ path: dir + '/login.png' });
  await page.type('input[type=\"email\"]', 'claudius@tallied.dev');
  await page.type('input[type=\"password\"]', 'demo123');
  await page.click('button[type=\"submit\"]');
  await new Promise(r => setTimeout(r, 3000));

  const pages = [
    ['/', 'dashboard.png'],
    ['/spending', 'spending.png'],
    ['/income', 'income.png'],
    ['/cash', 'cash.png'],
    ['/rsu', 'rsu.png'],
    ['/retirement', 'retirement.png'],
    ['/property', 'property.png'],
    ['/assets', 'assets.png'],
    ['/planning', 'planning.png'],
    ['/database', 'database.png'],
    ['/developer', 'api.png'],
    ['/settings', 'settings.png'],
    ['/guide', 'guide.png'],
  ];

  for (const [url, file] of pages) {
    await page.goto('http://localhost:5173' + url, { waitUntil: 'networkidle2', timeout: 15000 }).catch(() => {});
    await new Promise(r => setTimeout(r, 3000));
    await fullPageScreenshot(page, dir + '/' + file);
    console.log(file);
  }

  await browser.close();
})();
"
```

## Important notes

1. **Use the Node.js puppeteer API directly** (not the MCP puppeteer tool) to save screenshots to disk. The MCP `puppeteer_screenshot` tool returns images in-conversation but doesn't write files.

2. **Full-page captures require viewport resizing.** The app uses `overflow-y: auto` on the `<main>` element, so `fullPage: true` alone only captures the body (fixed at viewport height). Instead, resize the viewport to match the main element's `scrollHeight` before capturing.

3. **Seed test data first** (`make seed-test`) and optionally refresh asset/property values to populate historical charts.
