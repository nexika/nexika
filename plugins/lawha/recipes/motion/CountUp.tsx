/**
 * lawha recipe: a number that counts up once, when it comes into view.
 * Reduced motion: the final number at once. Screen readers get the final value from the start (as
 * visually hidden text; aria-label is not allowed on a plain span), so they never hear the count.
 */
import { animate, useInView } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useMotionTokens } from "./tokens";

export function CountUp({ value, className, format = (n) => String(Math.round(n)) }: { value: number; className?: string; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const t = useMotionTokens();
  const [shown, setShown] = useState(t.reduce ? value : 0);
  useEffect(() => {
    if (t.reduce) return setShown(value);
    if (!inView) return;
    const controls = animate(0, value, { duration: t.slow + 0.2, ease: t.ease, onUpdate: setShown });
    return () => controls.stop();
  }, [inView, t, value]);
  return (
    <span ref={ref} className={className} style={{ fontVariantNumeric: "tabular-nums" }}>
      <span className="sr-only">{format(value)}</span>
      <span aria-hidden="true">{format(shown)}</span>
    </span>
  );
}
