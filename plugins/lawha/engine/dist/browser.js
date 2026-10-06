import { chromium } from "playwright";
export function variantName(v) {
    return `${v.width}-${v.theme}-${v.dir}${v.motion === "reduce" ? "-reduced" : ""}`;
}
export async function launch() {
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
export async function openVariant(browser, opts, v) {
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
    await page.evaluate(() => document.fonts?.ready);
    await page.waitForTimeout(opts.settleMs ?? 800);
    return page;
}
export async function closePage(page) {
    await page.context().close();
}
