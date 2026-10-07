/**
 * lawha recipe: from skeleton to content without a jump.
 *
 *   <Swap ready={!!data} skeleton={<ListSkeleton />} minHeight="18rem">{data && <List items={data} />}</Swap>
 *
 * A cross-fade (opacity only) inside a box that keeps at least `minHeight`, so the page below does not
 * move when the content arrives (lawha check measures that as layout shift). Make the skeleton the
 * same shape as the content. Reduced motion: an instant swap.
 */
import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";
import { useMotionTokens } from "./tokens";

export function Swap({ ready, skeleton, children, minHeight, className }: { ready: boolean; skeleton: ReactNode; children: ReactNode; minHeight?: string; className?: string }) {
  const t = useMotionTokens();
  return (
    <div className={className} style={{ minHeight, display: "grid" }} aria-busy={!ready}>
      <AnimatePresence initial={false}>
        <motion.div
          key={ready ? "content" : "skeleton"}
          style={{ gridArea: "1 / 1" }}
          initial={t.reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: t.reduce ? 0 : t.fast } }}
          transition={{ duration: t.reduce ? 0 : t.base }}
        >
          {ready ? children : skeleton}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
