// Captures the four auth screens x {en, ar} x {desktop, tablet, mobile} via Chrome DevTools.
// Usage (stack must be running on :8080):
//   npm i --no-save puppeteer-core   # no browser download; uses your installed Chrome
//   node capture.cjs
const puppeteer = require("puppeteer-core");
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const BASE = process.env.BASE || "http://localhost:8080";
const FAKE_TOKEN = "a".repeat(43); // well-formed but unusable: only renders the reset form
const SIZES = { desktop: [1280, 800], tablet: [820, 1180], mobile: [390, 844] };
const SCREENS = ["sign-in", "sign-up", "forgot-password", "reset-password"];

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true });
  let n = 0;
  for (const lang of ["en", "ar"]) {
    for (const screen of SCREENS) {
      for (const [name, [width, height]] of Object.entries(SIZES)) {
        const page = await browser.newPage();
        await page.setViewport({ width, height, deviceScaleFactor: name === "mobile" ? 2 : 1, isMobile: name === "mobile", hasTouch: name !== "desktop" });
        const hash = screen === "reset-password" ? `#token=${FAKE_TOKEN}` : "";
        await page.goto(`${BASE}/${lang}/${screen}${hash}`, { waitUntil: "networkidle0" });
        await new Promise((r) => setTimeout(r, 400)); // let fonts and effects settle
        await page.screenshot({ path: `${lang}_${screen}_${name}.png` });
        await page.close();
        n++;
      }
    }
  }
  await browser.close();
  console.log(`${n} screenshots`);
})();
