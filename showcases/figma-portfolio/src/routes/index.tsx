import { createFileRoute } from "@tanstack/react-router";
import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/")({ component: Portfolio });

/** A short rise-and-fade on load; nothing moves when the visitor asks for reduced motion. */
function Rise({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.2, 0.7, 0.2, 1] }}
    >
      {children}
    </motion.div>
  );
}

const pill = "rounded-full font-poppins text-base";

function Nav() {
  return (
    <header className="flex h-[73px] items-center border-b-2 border-text-black bg-background-color-2 px-[21px] xl:h-[111px] xl:px-[100px]">
      <nav aria-label="Main" className="flex w-full items-center justify-between">
        <a href="/" className="trim-cap -my-2 py-2 font-poppins text-base font-semibold text-text-headings xl:text-2xl">
          Bernard Smith
        </a>
        <div className="flex items-center gap-6">
          <a href="#work" className="trim-cap -my-2 hidden py-2 font-poppins text-base text-text-black xl:block">
            Projects
          </a>
          <Button asChild className={`${pill} h-auto min-h-11 bg-buttons-secondary p-4 font-normal text-background-white hover:bg-buttons-secondary/85`}>
            <a href="#contact" className="font-medium">
              <span className="trim-cap block">Book Consultation</span>
            </a>
          </Button>
        </div>
      </nav>
    </header>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex items-center gap-2 md:w-full md:max-w-[448px] xl:w-auto xl:max-w-none">
      <span className="trim-cap md:trim-none xl:trim-cap font-poppins text-2xl font-semibold text-text-headings md:text-5xl xl:text-[64px]">{value}</span>
      <span className="trim-cap w-[95px] font-poppins text-xs text-text-dark-grey md:w-auto md:flex-1 md:text-2xl xl:w-[163px] xl:flex-none">{label}</span>
    </div>
  );
}

function Hero() {
  const portrait = (
    <img
      src="/figma/photo-1.png"
      alt="Bernard Smith smiling"
      className="h-full w-full object-cover"
      loading="eager"
    />
  );
  return (
    <section aria-labelledby="hero-title" className="flex flex-col gap-6 bg-background-color-1 p-4 md:h-[659px] md:flex-row md:gap-0 md:p-0 xl:h-[913px]">
      <div className="flex flex-col gap-6 md:flex-1 md:justify-center md:gap-[50px] md:p-8">
        <Rise className="flex flex-col gap-6 md:gap-4 xl:gap-8">
          <h1 id="hero-title" className="trim-cap md:trim-none xl:trim-cap w-[233px] font-poppins text-[32px] leading-10 font-medium text-text-headings md:w-[476px] md:text-5xl md:leading-[72px] md:font-semibold xl:w-full xl:text-[64px] xl:leading-[72px] xl:font-medium">
            Hey, I’m <br className="hidden md:inline xl:hidden" />
            Bernard Smith
          </h1>
          <div className="h-[530px] border-2 border-text-black md:hidden">{portrait}</div>
          <p className="trim-cap md:trim-none xl:trim-cap font-inter text-base leading-[23px] text-text-dark-grey md:font-poppins md:text-lg md:leading-[27px] xl:font-inter xl:text-2xl xl:leading-8">
            I help small businesses and entrepreneurs build meaningful digital experiences.
          </p>
        </Rise>
        <Rise delay={0.08} className="flex flex-col gap-[26px] md:gap-[50px]">
          <div className="flex items-center justify-center gap-[42px] md:flex-wrap md:justify-start md:gap-4 xl:gap-[42px]">
            <Stat value="3+" label="Years of experience" />
            <Stat value="1k+" label="Happy Customers" />
          </div>
          <Button asChild className={`${pill} h-[50px] w-full border border-b-[3px] border-text-black bg-buttons-primary font-semibold text-text-black uppercase hover:bg-buttons-primary/85 md:w-[222px]`}>
            <a href="#contact">
              <span className="trim-cap block">Work with me</span>
            </a>
          </Button>
        </Rise>
      </div>
      <div className="hidden border-s-2 border-text-black md:block md:flex-1">{portrait}</div>
    </section>
  );
}

const WORK = [
  { title: "UI/UX Designing", image: "/figma/photo-2.jpg", alt: "Cosmetic bottles and a tube on a stone stand" },
  { title: "Graphics Designing", image: "/figma/photo-3.jpg", alt: "A white paper shopping bag on a blue background" },
  { title: "App Concept", image: "/figma/photo-4.jpg", alt: "Folded business card mockups" },
  { title: "Medical Concept", image: "/figma/photo-6.jpg", alt: "A blue mug mockup" },
];

function Work() {
  return (
    <section id="work" aria-labelledby="work-title" className="flex flex-col gap-[23px] bg-background-color-3 p-4 md:items-center md:gap-[50px] md:p-8 xl:px-16">
      <div className="flex h-11 flex-col items-center justify-between md:h-auto md:justify-start md:gap-4">
        <p className="trim-cap font-poppins text-base font-medium text-text-blue md:text-2xl">Portfoilo</p>
        <h2 id="work-title" className="trim-cap font-poppins text-2xl font-semibold text-text-headings md:text-5xl">
          Recent Work
        </h2>
      </div>
      <ul className="grid w-full grid-cols-1 gap-6 md:grid-cols-2 md:gap-x-8">
        {WORK.map((item, i) => (
          <li key={item.title}>
            <Rise delay={0.05 * i} className="flex h-[341px] flex-col gap-2.5 rounded-[25px] border border-text-black bg-background-white px-[15px] py-4 md:h-[444px] md:gap-4 md:rounded-[29px] md:border-2 md:p-6 xl:h-[552px]">
              <img src={item.image} alt={item.alt} loading="lazy" className="h-[225px] w-full rounded-2xl border border-text-black object-cover md:h-[290px] xl:h-[377px]" />
              <div className="flex flex-col gap-0.5 md:gap-0">
                <h3 className="font-poppins text-base font-bold text-text-black md:text-lg xl:text-2xl">{item.title}</h3>
                <p className="font-poppins text-xs leading-[20.4px] tracking-[-0.12px] text-text-light-grey md:text-lg md:leading-[30.6px] md:tracking-[-0.18px]">
                  We start by getting to know our clients, their business goals, and their target audience.
                </p>
              </div>
            </Rise>
          </li>
        ))}
      </ul>
    </section>
  );
}

const CONTACT = [
  { label: "Email", value: "hello@Bernard Smith.com", icon: "/figma/email.svg" },
  { label: "Call", value: "(+44) 07827 275169", icon: "/figma/email-2.svg" },
  { label: "Website", value: "www.Bernard Smith.com", icon: "/figma/web.svg" },
];

function Contact() {
  return (
    <section id="contact" aria-labelledby="contact-title" className="flex flex-col gap-7 bg-background-color-4 p-4 md:items-center md:gap-[43px] md:border-b md:border-text-black md:px-[71px] md:py-[60px] xl:gap-[60px] xl:border-b-2 xl:px-[100px] xl:py-[95px]">
      <div className="flex flex-col items-center gap-4 text-center md:gap-[18px] xl:gap-[26px]">
        <h2 id="contact-title" className="trim-cap font-poppins text-2xl leading-[31.2px] font-semibold text-text-headings uppercase md:text-[34px] md:leading-[44.4px] xl:text-5xl xl:leading-[62.4px]">
          Let’s Create Together
        </h2>
        <p className="trim-cap w-[243px] font-poppins text-xs text-text-dark-grey md:w-[351px] md:text-[11.4px] xl:w-[494px] xl:text-base">
          Please fill out the form on this section to contact with me. Or call between 9:00 a.m. and 8:00 p.m. ET, Monday through Friday
        </p>
      </div>
      <ul className="flex flex-col gap-4 md:flex-row md:flex-wrap md:justify-center md:gap-x-[53px] lg:flex-nowrap xl:gap-[74px]">
        {CONTACT.map((c) => (
          <li key={c.label} className="flex items-center justify-center gap-3 rounded-lg bg-background-white p-6 ring-1 ring-text-black ring-inset md:justify-start md:gap-[9px] md:rounded-2xl md:p-[17px] md:ring-[0.7px] xl:gap-3 xl:p-6 xl:ring-1">
            <span className="flex h-14 w-[71px] items-center justify-center rounded-[3px] border border-text-black bg-buttons-primary md:w-[65px] md:rounded border-[0.7px] xl:h-[79px] xl:w-[91px] xl:rounded-md xl:border">
              <img src={c.icon} alt="" className="size-7 md:size-[26px] xl:size-9" />
            </span>
            <span className="flex w-[213px] flex-col gap-[7px] md:w-[151px] md:gap-[5px] xl:w-[213px] xl:gap-[7px]">
              <span className="font-inter text-base leading-[1.21] font-semibold text-text-headings md:text-[14.2px] xl:text-xl">{c.label}</span>
              <span className="font-poppins text-xs leading-[15.6px] text-text-dark-grey md:text-[11.4px] md:leading-[14.8px] xl:text-base xl:leading-[20.8px]">{c.value}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Footer() {
  return (
    <footer className="flex h-[74px] items-center justify-center bg-text-black md:h-[53px] xl:h-auto xl:py-[30px]">
      <p className="trim-cap font-dm-sans text-xs leading-[26px] text-background-white md:text-[11.4px] md:leading-[18.5px] xl:text-base xl:leading-[26px]">
        © 2024 Bernard Smith. All rights reserved.
      </p>
    </footer>
  );
}

function Portfolio() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <Work />
        <Contact />
      </main>
      <Footer />
    </>
  );
}
