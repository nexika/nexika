import { useId, useState, type ReactNode } from "react";
import { asset, column, gutter, Logo } from "./ui";

function FoldRow({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div>
      <h2>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((o) => !o)}
          className="-my-2 flex w-full items-center gap-8 py-2 text-start focus-visible:outline-2 focus-visible:outline-primary"
        >
          <span className={`${heading} flex-1`}>{title}</span>
          <img
            src={asset("arrow-circle-down.svg")}
            alt=""
            width={24}
            height={24}
            className={`size-6 motion-safe:transition-transform ${open ? "rotate-180" : ""}`}
          />
        </button>
      </h2>
      <div id={id} hidden={!open} className="pt-6">
        {children}
      </div>
    </div>
  );
}

export function Newsletter() {
  return (
    <div className={`relative ${gutter} md:mt-[109px] xl:mt-[177px]`}>
      <section
        aria-labelledby="newsletter-title"
        className={`${column} relative flex flex-col gap-16 rounded-[32px] bg-yellow/8 px-8 py-16 md:px-16 md:py-32`}
      >
        <img
          src={asset("deco-dots.svg")}
          alt=""
          aria-hidden="true"
          className="pointer-events-none absolute -top-[67px] -left-[35px] hidden w-[184px] md:block"
        />
        <div className="relative flex flex-col gap-8 text-center">
          <p className="font-bold uppercase text-secondary-text text-[16px] leading-[19.2px] tracking-[3.2px] md:text-[23px] md:leading-[27.6px] md:tracking-[4.6px]">
            subscribe to our newsletter
          </p>
          <h2
            id="newsletter-title"
            className="font-bold text-grey-scale-black text-[32px] leading-[38.4px] md:text-[40px] md:leading-[48px] xl:text-[55px] xl:leading-[66px]"
          >
            Prepare yourself &amp; let’s explore the beauty of the world
          </h2>
        </div>
        <form
          className="relative flex flex-col gap-8 md:flex-row xl:gap-16"
          onSubmit={(e) => e.preventDefault()}
        >
          <label className="flex items-center gap-4 rounded-2xl bg-white px-8 focus-within:outline-2 focus-within:outline-primary md:min-h-24 md:flex-1 md:rounded-[32px]">
            <img src={asset("message-1.svg")} alt="" width={32} height={32} className="size-6 md:size-8" />
            <span className="sr-only">Your Email</span>
            <input
              type="email"
              name="email"
              autoComplete="email"
              required
              placeholder="Your Email"
              className="w-full min-w-0 self-stretch bg-transparent py-6 text-[14px] leading-[16.8px] font-bold text-grey-scale-black outline-none placeholder:text-grey-scale-black-75 md:py-8 md:text-[23px] md:leading-[27.6px]"
            />
          </label>
          <button
            type="submit"
            className="flex items-center justify-center rounded-2xl bg-primary px-16 py-6 text-[16px] leading-[19.2px] font-bold text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary md:rounded-[32px] md:py-8 md:text-[23px] md:leading-[27.6px]"
          >
            Subscribe
          </button>
        </form>
      </section>
    </div>
  );
}

const columns = [
  { title: "Company", mobileTitle: "Company", links: ["About", "Career", "Mobile"] },
  { title: "Contact", mobileTitle: "Contact Us", links: ["Why Travlog?", "Partner with us", "FAQ’s", "Blog"] },
];

const socials = [
  { icon: "group-3.svg", label: "Facebook" },
  { icon: "group-4.svg", label: "Twitter" },
  { icon: "group-8.svg", label: "Instagram" },
];

const linkText = "font-inter text-[18px] leading-[28.8px] text-grey-scale-black-75";
const heading = "text-[23px] leading-[27.6px] font-bold text-grey-scale-black";

function MeetUs() {
  return (
    <>
      <a href="tel:+00921234567890" className={linkText}>
        +00 92 1234 56789
      </a>
      <a href="mailto:info@travlog.com" className={linkText}>
        info@travlog.com
      </a>
      <address className="flex flex-col gap-2 not-italic">
        <span className={linkText}>205. R Street, New York</span>
        <span className={linkText}>BD23200</span>
      </address>
    </>
  );
}

export function Footer() {
  return (
    <footer className={`relative ${gutter} md:mt-16`}>
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 -top-[192px] hidden h-[400px] overflow-hidden md:block">
        <img
          src={asset("deco-waves.svg")}
          alt=""
          className="absolute top-[117px] left-[calc(50%+430px)] w-[332px] max-w-none xl:top-0 xl:left-[calc(50%+608px)]"
        />
      </div>
      <div className={`${column} relative flex flex-col gap-16 py-8 md:py-16 xl:flex-row`}>
        <div className="flex w-full flex-col gap-8 xl:flex-1 xl:gap-16">
          <div className="flex w-full flex-col gap-8">
            <Logo />
            <p className="text-[16px] leading-[25.6px] font-[450] text-grey-scale-black-50 md:text-[23px] md:leading-[36.8px]">
              Contrary to popular belief, Lorem Ipsum is not simply random text. It has roots in a piece of classical
              Latin literature from 45 BC.
            </p>
          </div>
          <ul className="flex gap-8">
            {socials.map((s) => (
              <li key={s.label}>
                <a href="#" aria-label={s.label} className="-m-1.5 block p-1.5">
                  <img src={asset(s.icon)} alt="" width={32} height={32} className="size-8" />
                </a>
              </li>
            ))}
          </ul>
        </div>

        {/* Phones: each column folds into a row that opens. */}
        <div className="flex flex-col gap-16 md:hidden">
          {columns.map((c) => (
            <FoldRow key={c.title} title={c.mobileTitle}>
              <ul className="flex flex-col gap-4">
                {c.links.map((l) => (
                  <li key={l}>
                    <a href="#" className={`${linkText} block py-1`}>
                      {l}
                    </a>
                  </li>
                ))}
              </ul>
            </FoldRow>
          ))}
          <FoldRow title="Meet Us">
            <div className="flex flex-col gap-4">
              <MeetUs />
            </div>
          </FoldRow>
        </div>

        {/* Tablets and desktops: three columns. */}
        <div className="hidden w-full gap-8 md:flex xl:flex-1">
          {columns.map((c) => (
            <nav key={c.title} aria-label={c.title} className="flex flex-1 flex-col gap-8">
              <h2 className={heading}>{c.title}</h2>
              {c.links.map((l) => (
                <a key={l} href="#" className={linkText}>
                  {l}
                </a>
              ))}
            </nav>
          ))}
          <div className="flex flex-1 flex-col gap-8">
            <h2 className={heading}>Meet Us</h2>
            <MeetUs />
          </div>
        </div>
      </div>
    </footer>
  );
}
