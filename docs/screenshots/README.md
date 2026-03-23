     1	# Screenshots
     2	
     3	These screenshots are taken with Puppeteer using the Claudius Banks test persona.
     4	
     5	## How to regenerate
     6	
     7	From the project root, with the backend running (`make dev`):
     8	
     9	```bash
    10	node -e "
    11	const puppeteer = require('puppeteer');
    12	(async () => {
    13	  const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
    14	  const page = await browser.newPage();
    15	  await page.setViewport({ width: 1400, height: 900 });
    16	  const dir = 'docs/screenshots';
    17	  
    18	  // Login as Claudius Banks
    19	  await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle2' });
    20	  await page.screenshot({ path: dir + '/login.png' });
    21	  await page.type('input[type=\"email\"]', 'claudius@tallied.dev');
    22	  await page.type('input[type=\"password\"]', 'demo123');
    23	  await page.click('button[type=\"submit\"]');
    24	  await new Promise(r => setTimeout(r, 3000));
    25	  
    26	  const pages = [
    27	    ['/', 'dashboard.png'],
    28	    ['/spending', 'spending.png'],
    29	    ['/income', 'income.png'],
    30	    ['/cash', 'cash.png'],
    31	    ['/rsu', 'rsu.png'],
    32	    ['/retirement', 'retirement.png'],
    33	    ['/property', 'property.png'],
    34	    ['/assets', 'assets.png'],
    35	    ['/planning', 'planning.png'],
    36	    ['/database', 'database.png'],
    37	    ['/developer', 'api.png'],
    38	    ['/settings', 'settings.png'],
    39	    ['/guide', 'guide.png'],
    40	  ];
    41	  
    42	  for (const [url, file] of pages) {
    43	    await page.goto('http://localhost:5173' + url, { waitUntil: 'networkidle2', timeout: 10000 }).catch(() => {});
    44	    await new Promise(r => setTimeout(r, 2000));
    45	    await page.screenshot({ path: dir + '/' + file });
    46	    console.log(file);
    47	  }
    48	  
    49	  await browser.close();
    50	})();
    51	"
    52	```
    53	
    54	**Important:** Use the Node.js puppeteer API directly (not the MCP tool) to save screenshots to disk. The MCP puppeteer_screenshot tool returns images in-conversation but doesn't write files.
