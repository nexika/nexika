/**
 * lawha recipe: toasts that slide up, stack, and leave on their own.
 *
 *   <ToastProvider> <App /> <Toaster /> </ToastProvider>
 *   const toast = useToast();  toast("Saved");
 *
 * Announced politely to screen readers (role="status"). Each stays 5 seconds, longer while the pointer
 * or keyboard focus is on it, and has a close button. Reduced motion: they appear and go at once.
 */
import { AnimatePresence, motion } from "motion/react";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { transition, useMotionTokens } from "./tokens";

interface Toast { id: number; text: string }
const Ctx = createContext<{ toasts: Toast[]; push: (text: string) => void; drop: (id: number) => void }>({ toasts: [], push: () => undefined, drop: () => undefined });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const push = useCallback((text: string) => setToasts((all) => [...all.slice(-2), { id: next.current++, text }]), []);
  const drop = useCallback((id: number) => setToasts((all) => all.filter((t) => t.id !== id)), []);
  return <Ctx.Provider value={{ toasts, push, drop }}>{children}</Ctx.Provider>;
}

export const useToast = () => useContext(Ctx).push;

function Item({ toast }: { toast: Toast }) {
  const { drop } = useContext(Ctx);
  const t = useMotionTokens();
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (held) return;
    const timer = setTimeout(() => drop(toast.id), 5000);
    return () => clearTimeout(timer);
  }, [held, drop, toast.id]);
  return (
    <motion.li
      layout={!t.reduce}
      initial={t.reduce ? false : { opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={t.reduce ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0, scale: 0.98, transition: { duration: t.fast } }}
      transition={transition(t, "base")}
      onPointerEnter={() => setHeld(true)} onPointerLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)} onBlur={() => setHeld(false)}
      className="flex items-center gap-3 rounded-[var(--radius-card,8px)] border border-border bg-card px-4 py-2 text-card-foreground shadow-lg"
    >
      <span className="min-w-0 flex-1">{toast.text}</span>
      <button type="button" onClick={() => drop(toast.id)} className="grid size-11 shrink-0 place-items-center" aria-label="Dismiss">
        <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
      </button>
    </motion.li>
  );
}

export function Toaster() {
  const { toasts } = useContext(Ctx);
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex justify-center sm:inset-x-auto sm:end-4">
      <ul className="pointer-events-auto grid w-full max-w-sm gap-2">
        <AnimatePresence initial={false}>{toasts.map((t) => <Item key={t.id} toast={t} />)}</AnimatePresence>
      </ul>
    </div>
  );
}
