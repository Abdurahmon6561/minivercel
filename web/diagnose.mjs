import { chromium } from "playwright";

const browser = await chromium.launch();
const url = "http://localhost:5183/";

const widths = [375, 414, 1024];

for (const width of widths) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);

  const metrics = await page.evaluate(() => {
    const doc = document.documentElement;
    return {
      scrollWidth: doc.scrollWidth,
      innerWidth: window.innerWidth,
      overflowing: doc.scrollWidth > window.innerWidth + 1,
    };
  });

  // find the widest offender
  const offenders = await page.evaluate(() => {
    const vw = window.innerWidth;
    const all = Array.from(document.querySelectorAll("body *"));
    const found = [];
    for (const el of all) {
      const rect = el.getBoundingClientRect();
      if (rect.right > vw + 1 || rect.left < -1) {
        found.push({
          tag: el.tagName,
          cls: el.className && typeof el.className === "string" ? el.className.slice(0, 120) : "",
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          width: Math.round(rect.width),
        });
      }
    }
    return found.slice(0, 15);
  });

  console.log(`\n=== width=${width} ===`);
  console.log(metrics);
  if (offenders.length) {
    console.log("offenders:", JSON.stringify(offenders, null, 2));
  }

  await page.screenshot({ path: `C:\\Users\\abduq\\AppData\\Local\\Temp\\claude\\d--Vercel\\b56183f1-992e-4710-aef5-930746e7cf70\\scratchpad\\hero-${width}.png` });

  // scroll to second section
  const secondSectionBox = await page.evaluate(() => {
    const el = document.querySelector("#how-it-works");
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { top: r.top + window.scrollY, height: r.height };
  });
  if (secondSectionBox) {
    await page.evaluate((top) => window.scrollTo(0, top), secondSectionBox.top);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `C:\\Users\\abduq\\AppData\\Local\\Temp\\claude\\d--Vercel\\b56183f1-992e-4710-aef5-930746e7cf70\\scratchpad\\second-${width}.png` });
  }

  await page.close();
}

await browser.close();
