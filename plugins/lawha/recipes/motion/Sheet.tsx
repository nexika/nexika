/**
 * lawha recipe: a side sheet (drawer) built on the native <dialog>.
 *
 *   <Sheet open={open} onClose={() => setOpen(false)} title="Filters">…</Sheet>
 *
 * The native dialog gives focus trapping, Escape to close and the backdrop for free. The sheet slides
 * in from the end of the line: the right in English, the left in Arabic. Reduced motion: it appears
 * at once. Closing animates out before the dialog is removed.
 */
import { AnimatePresence, motion } from "motion/react";
import { type ReactNode, useEffect, useId, useRef } from "react";
import { inline, transition, useMotionTokens } from "./tokens";

function Panel({ onClose, title, children, className }: { onClose: () => void; title: string; children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  const t = useMotionTokens();
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);
  const away = inline(t, 48);
  return (
    <motion.dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(e) => { e.preventDefault(); onClose(); }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      className={className ?? "m-0 ms-auto h-dvh max-h-none w-[min(26rem,100vw)] max-w-none bg-background p-0 text-foreground shadow-2xl backdrop:bg-black/40"}
      initial={t.reduce ? false : { opacity: 0, x: away }}
      animate={{ opacity: 1, x: 0 }}
      exit={t.reduce ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0, x: away }}
      transition={transition(t, "base")}
    >
      <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-3">
        <h2 id={titleId} className="text-lg font-semibold">{title}</h2>
        <button type="button" onClick={onClose} className="grid size-11 place-items-center rounded-md" aria-label="Close">
          <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>
      <div className="p-5">{children}</div>
    </motion.dialog>
  );
}

export function Sheet({ open, ...props }: { open: boolean; onClose: () => void; title: string; children: ReactNode; className?: string }) {
  return <AnimatePresence>{open && <Panel key="sheet" {...props} />}</AnimatePresence>;
}
