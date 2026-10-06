import { chromium, type Browser, type Page } from "playwright";

export interface Variant {
  width: number;
  theme: "light" | "dark";
  dir: "ltr" | "rtl";
  motion: "full" | "reduce";
}

export interface LoadOptions {
  url: string;
  /** Used for dir=rtl instead of forcing dir="rtl" on <html>, when the app has its own RTL route. */
  rtlUrl?: string;
  height?: number;
  settleMs?: number;
}

export function variantName(v: Variant): string {
  return `${v.width}-${v.theme}-${v.dir}${v.motion === "reduce" ? "-reduced" : ""}`;
}

export async function launch(): Promise<Browser> {
  return chromium.launch();
}

/** Track layout shifts from the very first paint, before any page script runs. */
const CLS_SCRIPT = `
  window.__lawhaCls = 0;
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        if (e.hadRecentInput) continue;
        window.__lawhaCls += e.value;
        // Which elements moved, so the fix can name them.
        window.__lawhaShifts = window.__lawhaShifts || {};
        for (const s of e.sources || []) {
          const n = s.node && s.node.nodeType === 1 ? s.node : s.node && s.node.parentElement;
          if (!n) continue;
          const name = n.tagName.toLowerCase() + (n.id ? "#" + n.id : "") + [...n.classList].slice(0, 2).map((c) => "." + c).join("");
          window.__lawhaShifts[name] = (window.__lawhaShifts[name] || 0) + e.value;
        }
      }
    }).observe({ type: "layout-shift", buffered: true });
  } catch (e) {}
`;

export async function openVariant(browser: Browser, opts: LoadOptions, v: Variant): Promise<Page> {
  const context = await browser.newContext({
    viewport: { width: v.width, height: opts.height ?? 900 },
    colorScheme: v.theme,
    reducedMotion: v.motion === "reduce" ? "reduce" : "no-preference",
    deviceScaleFactor: 1,
    hasTouch: v.width <= 767,
    isMobile: false,
  });
  const page = await context.newPage();
  await page.addInitScript(CLS_SCRIPT);
  const url = v.dir === "rtl" && opts.rtlUrl ? opts.rtlUrl : opts.url;
  await page.goto(url, { waitUntil: "load", timeout: 60_000 });
  if (v.dir === "rtl" && !opts.rtlUrl) {
    await page.evaluate(() => document.documentElement.setAttribute("dir", "rtl"));
  }
  // Let fonts, images and entrance animations settle before measuring.
  await page.evaluate(() => (document as Document & { fonts?: FontFaceSet }).fonts?.ready);
  await page.waitForTimeout(opts.settleMs ?? 800);
  return page;
}

export async function closePage(page: Page): Promise<void> {
  await page.context().close();
}
