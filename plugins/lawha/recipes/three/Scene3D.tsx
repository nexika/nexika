/**
 * lawha recipe: the safe container for any Three.js scene (React Three Fiber).
 *
 * - "reduce motion": one still frame (frameloop="demand"), never a running loop;
 * - off screen or in a hidden tab: nothing is drawn (frameloop="never");
 * - pixel density capped at 2 (phones would otherwise draw 9x the pixels);
 * - no WebGL: the `fallback` (a CSS gradient) instead of an empty box;
 * - decorative: hidden from screen readers; the page's content never lives inside the canvas.
 *
 * Needs: npm i three @react-three/fiber motion
 */
import { Canvas, type CanvasProps } from "@react-three/fiber";
import { useReducedMotion } from "motion/react";
import { type ReactNode, useEffect, useRef, useState } from "react";

function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export function Scene3D({ children, fallback, className, camera, ...props }: { children: ReactNode; fallback: ReactNode; className?: string } & Omit<CanvasProps, "children">) {
  const reduce = useReducedMotion();
  const box = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(true);
  const [webgl, setWebgl] = useState(true);

  useEffect(() => setWebgl(hasWebGL()), []);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setVisible(!!entry?.isIntersecting && !document.hidden), { rootMargin: "100px" });
    io.observe(el);
    const onVis = () => setVisible(!document.hidden && el.getBoundingClientRect().bottom > 0);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return (
    <div ref={box} className={className} aria-hidden="true" style={{ position: "relative" }}>
      {webgl ? (
        <Canvas
          frameloop={reduce ? "demand" : visible ? "always" : "never"}
          dpr={[1, 2]}
          gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
          camera={camera ?? { position: [0, 0, 5], fov: 45 }}
          {...props}
        >
          {children}
        </Canvas>
      ) : (
        fallback
      )}
    </div>
  );
}

/** A colour from the page's design tokens (`--primary`, `--accent`...), so the scene follows the theme. */
export function token(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}
