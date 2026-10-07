import type { ReactNode } from "react";

export const asset = (name: string) => `/assets/${name}`;

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

export function Logo() {
  return (
    <a href="#" className="flex shrink-0 items-center gap-4" aria-label="Travlog home">
      <img src={asset("logo.svg")} alt="" width={40} height={40} className="size-10" />
      <span className="font-display text-[24px] leading-10 font-black text-ink">Travlog</span>
    </a>
  );
}

/** Pink, spaced-out uppercase label above each section title. */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p
      className={cx(
        "font-display text-[16px] leading-[1.2] font-bold tracking-[3.2px] text-secondary uppercase md:text-[23px] md:tracking-[4.6px]",
        className,
      )}
    >
      {children}
    </p>
  );
}

export function SectionTitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <h2
      className={cx(
        "font-display text-[32px] leading-[1.2] font-bold text-ink md:text-[40px] xl:text-[44px]",
        className,
      )}
    >
      {children}
    </h2>
  );
}

/** Round carousel arrow: outlined "previous", filled purple "next". 64px on phones, 100px from tablet up. */
export function ArrowButton({
  direction,
  onClick,
  label,
}: {
  direction: "prev" | "next";
  onClick?: () => void;
  label: string;
}) {
  const next = direction === "next";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={cx(
        "grid size-16 shrink-0 cursor-pointer place-items-center rounded-full transition-transform hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary md:size-[100px]",
        next ? "bg-primary" : "border border-ink/10 bg-white",
      )}
    >
      <span className={cx("relative block size-[15.36px] md:size-6", next && "-scale-x-100")}>
        <span className="absolute inset-[25.21%_12.5%_25.21%_14.23%]">
          <img
            src={asset(next ? "arrow-left-white.svg" : "arrow-left.svg")}
            alt=""
            className="block size-full max-w-none"
          />
        </span>
      </span>
    </button>
  );
}
