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
  /** A Playwright storage state (cookies and local storage) saved from a signed-in browser. */
  storageState?: string;
  /** Cookies ("name=value") and headers ("Name: value") for the page's own origin only. */
  cookies?: string[];
  headers?: string[];
  /** Wait for this selector, and optionally for the network to go quiet, before measuring. */
  waitFor?: string;
  networkIdle?: boolean;
}

function parseHeaders(lines: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of lines) {
    const cut = line.indexOf(":");
    if (cut > 0) out[line.slice(0, cut).trim().toLowerCase()] = line.slice(cut + 1).trim();
  }
  return out;
}

export function variantName(v: Variant): string {
  return `${v.width}-${v.theme}-${v.dir}${v.motion === "reduce" ? "-reduced" : ""}`;
}

export async function launch(): Promise<Browser> {
  return chromium.launch();
}

/** Track layout shifts and every animation started, from the very first paint, before any page script runs. */
const CLS_SCRIPT = `
  window.__lawhaAnims = [];
  (function () {
    const name = (el) => el && el.tagName ? el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + [...el.classList].slice(0, 2).map((c) => "." + c).join("") : "(unknown)";
    const log = (el, duration, iterations, delay, props) => {
      if (window.__lawhaAnims.length >= 400) return;
      const r = el && el.getBoundingClientRect ? el.getBoundingClientRect() : { width: 0, height: 0 };
      window.__lawhaAnims.push({ selector: name(el), duration: Number(duration) || 0, iterations: iterations === Infinity ? -1 : Number(iterations) || 1, delay: Number(delay) || 0, props, area: Math.round(r.width * r.height) });
    };
    // Motion and other libraries animate through element.animate (the Web Animations API).
    const original = Element.prototype.animate;
    Element.prototype.animate = function (keyframes, options) {
      try {
        const o = typeof options === "number" ? { duration: options } : options || {};
        const frames = Array.isArray(keyframes) ? keyframes : [keyframes || {}];
        const props = [...new Set(frames.flatMap((f) => Object.keys(f || {})).filter((k) => !["offset", "easing", "composite"].includes(k)))];
        log(this, o.duration, o.iterations, o.delay, props);
      } catch (e) {}
      return original.apply(this, arguments);
    };
    // CSS animations.
    document.addEventListener("animationstart", (e) => {
      try {
        const s = getComputedStyle(e.target);
        const i = s.animationIterationCount === "infinite" ? Infinity : parseFloat(s.animationIterationCount);
        log(e.target, parseFloat(s.animationDuration) * 1000, i, parseFloat(s.animationDelay) * 1000, ["@" + e.animationName]);
      } catch (err) {}
    }, true);
  })();
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
    ...(opts.storageState ? { storageState: opts.storageState } : {}),
  });
  const url = v.dir === "rtl" && opts.rtlUrl ? opts.rtlUrl : opts.url;
  const origin = (() => { try { return new URL(url).origin; } catch { return "null"; } })();
  if (opts.cookies?.length && origin !== "null") {
    await context.addCookies(opts.cookies.filter((c) => c.includes("=")).map((c) => {
      const cut = c.indexOf("=");
      return { name: c.slice(0, cut).trim(), value: c.slice(cut + 1).trim(), url: origin };
    }));
  }
  const headers = parseHeaders(opts.headers ?? []);
  if (Object.keys(headers).length && origin !== "null") {
    // Only to the page's own origin: a token must not reach a CDN or an analytics host.
    await context.route("**/*", (route) => {
      const request = route.request();
      const same = (() => { try { return new URL(request.url()).origin === origin; } catch { return false; } })();
      return same ? route.continue({ headers: { ...request.headers(), ...headers } }) : route.continue();
    });
  }
  const page = await context.newPage();
  await page.addInitScript(CLS_SCRIPT);
  await page.goto(url, { waitUntil: "load", timeout: 60_000 });
  if (opts.networkIdle) await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => undefined);
  if (opts.waitFor) await page.waitForSelector(opts.waitFor, { state: "attached", timeout: 30_000 });
  if (v.dir === "rtl" && !opts.rtlUrl) {
    await page.evaluate(() => document.documentElement.setAttribute("dir", "rtl"));
  }
  // Let fonts, images and entrance animations settle before measuring.
  await page.evaluate(() => (document as Document & { fonts?: FontFaceSet }).fonts?.ready);
  await page.waitForTimeout(opts.settleMs ?? 800);
  await revealAll(page);
  return page;
}

/**
 * Scroll through the whole page once, so sections that appear when scrolled to (whileInView,
 * IntersectionObserver, lazy images) are shown before anything is measured or photographed, then go
 * back to the top. Without this, a full-page screenshot shows those sections blank.
 */
export async function revealAll(page: Page): Promise<void> {
  const step = Math.round((page.viewportSize()?.height ?? 900) * 0.8);
  for (let i = 0; i < 40; i++) {
    const done = await page.evaluate((s) => {
      window.scrollBy(0, s);
      return window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2;
    }, step);
    await page.waitForTimeout(120);
    if (done) break;
  }
  await page.waitForTimeout(900); // the last entrances finish (lawha's slowest token is 700ms)
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(300);
}

/**
 * Where the page ended up, when that is not where it was sent: a login wall, a locale redirect.
 * Origin and path are compared (a trailing slash, the query and the hash do not count), so
 * /private landing on /login.html?next=/private is caught.
 */
export function redirectedTo(requested: string, final: string): string | null {
  const key = (u: string) => {
    try {
      const p = new URL(u);
      return `${p.origin === "null" ? p.protocol : p.origin}${p.pathname.replace(/\/+$/, "") || "/"}`;
    } catch {
      return u;
    }
  };
  return key(requested) === key(final) ? null : final;
}

export async function closePage(page: Page): Promise<void> {
  await page.context().close();
}
