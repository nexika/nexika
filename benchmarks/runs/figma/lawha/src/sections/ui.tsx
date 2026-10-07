import type { ReactNode } from "react";

export const asset = (name: string) => `/design-assets/${name}`;

/** The page column: 398px on phones (16px sides), 896px on tablets (64px sides), 1184px on desktops. */
export const column = "mx-auto w-full max-w-[1184px]";
export const gutter = "px-4 md:px-16 xl:px-0";

export function Eyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <p
      className={`w-full font-bold uppercase text-secondary-text text-[16px] leading-[19.2px] tracking-[3.2px] md:text-[23px] md:leading-[27.6px] md:tracking-[4.6px] ${className}`}
    >
      {children}
    </p>
  );
}

export function SectionTitle({ id, children, className = "" }: { id?: string; children: ReactNode; className?: string }) {
  return (
    <h2
      id={id}
      className={`w-full font-bold tracking-[-0.02em] text-grey-scale-black text-[32px] leading-[38.4px] md:text-[40px] md:leading-[48px] xl:text-[44px] xl:leading-[52.8px] ${className}`}
    >
      {children}
    </h2>
  );
}

export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`flex items-center gap-4 ${className}`}>
      <img src={asset("vector-11.svg")} alt="" width={40} height={40} className="size-10" />
      <span className="font-black text-[24px] leading-[40px] text-black">Travlog</span>
    </span>
  );
}

const arrowShadow =
  "shadow-[0_7px_16px_rgba(0,0,0,0.07),0_29px_29px_rgba(0,0,0,0.06),0_65px_39px_rgba(0,0,0,0.04),0_116px_46px_rgba(0,0,0,0.01)]";

/** Round previous / next buttons: 64px on phones, 100px from tablets up. */
export function ArrowButton({
  direction,
  label,
  onClick,
  className = "",
}: {
  direction: "prev" | "next";
  label: string;
  onClick?: () => void;
  className?: string;
}) {
  const prev = direction === "prev";
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={`grid size-16 shrink-0 place-items-center rounded-full md:size-[100px] ${
        prev ? "bg-white ring-1 ring-inset ring-grey-scale-black-10" : `bg-primary ${arrowShadow}`
      } focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary ${className}`}
    >
      <img
        src={asset(prev ? "arrow-left-1.svg" : "arrow-left-2.svg")}
        alt=""
        width={24}
        height={24}
        className="size-[15px] md:size-6 rtl:-scale-x-100"
      />
    </button>
  );
}
