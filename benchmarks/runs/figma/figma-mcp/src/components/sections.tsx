import { useRef, useState, type CSSProperties, type FormEvent } from "react";
import { ArrowButton, asset, cx, Eyebrow, Logo, SectionTitle } from "./ui";

/* ------------------------------------------------------------------ Header */

const NAV = ["Home", "Discover", "Special Deals", "Contact"];

function AuthButtons({ className }: { className?: string }) {
  return (
    <div className={cx("items-start", className)}>
      <a href="#" className="rounded-full bg-white px-8 py-4 font-display text-[14px] leading-[1.2] font-bold text-dark">
        Log In
      </a>
      <a
        href="#"
        className="rounded-full bg-primary px-8 py-4 font-display text-[14px] leading-[1.2] font-bold text-light transition-colors hover:bg-primary/90"
      >
        Sign Up
      </a>
    </div>
  );
}

/**
 * Phone: logo · menu. Tablet: menu · logo · auth. Desktop: logo · links · auth.
 * Below desktop the menu button opens the links (and, on phones, the auth buttons).
 */
export function Header() {
  const [open, setOpen] = useState(false);

  return (
    <header className="relative z-30">
      <div className="shell flex items-center justify-between py-8">
        <button
          type="button"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          aria-controls="mobile-nav"
          onClick={() => setOpen((v) => !v)}
          className="order-last size-12 shrink-0 cursor-pointer md:order-first xl:hidden"
        >
          <img src={asset("menu.svg")} alt="" width={48} height={48} className="size-12" />
        </button>

        <Logo />

        <nav aria-label="Main" className="hidden xl:block">
          <ul className="flex gap-16 font-display text-[14px] leading-[1.2] font-bold">
            {NAV.map((item, i) => (
              <li key={item}>
                <a
                  href="#"
                  aria-current={i === 0 ? "page" : undefined}
                  className={cx("transition-colors hover:text-dark", i === 0 ? "text-dark" : "text-ink/50")}
                >
                  {item}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <AuthButtons className="hidden md:flex" />
      </div>

      {open && (
        <nav id="mobile-nav" aria-label="Main" className="shell absolute inset-x-0 top-full xl:hidden">
          <div className="rounded-[32px] border border-ink/10 bg-white p-6 shadow-[0_34px_37.5px_rgba(0,0,0,0.07)]">
            <ul className="flex flex-col gap-1 font-display text-[16px] leading-[1.2] font-bold">
              {NAV.map((item, i) => (
                <li key={item}>
                  <a
                    href="#"
                    onClick={() => setOpen(false)}
                    className={cx(
                      "block rounded-2xl px-4 py-3 hover:bg-ink/5",
                      i === 0 ? "text-dark" : "text-ink/50",
                    )}
                  >
                    {item}
                  </a>
                </li>
              ))}
            </ul>
            <AuthButtons className="mt-4 flex justify-center border-t border-ink/10 pt-4 md:hidden" />
          </div>
        </nav>
      )}
    </header>
  );
}

/* -------------------------------------------------------------------- Hero */

/** Position inside the 772×713 collage, as percentages so it scales down on phones. */
const at = (x: number, y: number, w: number, h?: number): CSSProperties => ({
  left: `${(x / 772) * 100}%`,
  top: `${(y / 713) * 100}%`,
  width: `${(w / 772) * 100}%`,
  ...(h !== undefined && { height: `${(h / 713) * 100}%` }),
});

const floatShadow =
  "shadow-[0_19px_19px_rgba(0,0,0,0.09),0_43px_26px_rgba(0,0,0,0.05),0_77px_31px_rgba(0,0,0,0.01)]";

function HeroCollage() {
  return (
    <div className="@container relative aspect-[772/713] w-full max-w-[772px] shrink-0 xl:w-[772px]">
      <img src={asset("hero-layer.svg")} alt="" className="absolute block max-w-none" style={at(0, 0, 772, 287.383)} />
      <img
        src={asset("hero-1.jpg")}
        alt="White-washed stairs leading down to a blue sea"
        className="absolute rounded-[4.145cqw] bg-[#d9d9d9] object-cover"
        style={at(91, 75, 272, 300)}
      />
      <img
        src={asset("hero-2.jpg")}
        alt="A hiker resting on a mountain ridge"
        className="absolute rounded-[4.145cqw] bg-[#d9d9d9] object-cover"
        style={at(91, 407, 272, 300)}
      />
      <img
        src={asset("hero-3.jpg")}
        alt="A traveller with a backpack photographing a city"
        className="absolute rounded-[4.145cqw] bg-[#d9d9d9] object-cover"
        style={at(394, 191, 272, 400)}
      />
      <span
        className={cx("absolute grid aspect-square place-items-center rounded-full bg-secondary", floatShadow)}
        style={at(56, 341, 64)}
      >
        <img src={asset("send.svg")} alt="" className="w-1/2" />
      </span>
      <span
        className={cx("absolute grid aspect-square place-items-center rounded-full bg-orange", floatShadow)}
        style={at(474, 649, 64)}
      >
        <img src={asset("add-user.svg")} alt="" className="w-1/2" />
      </span>
      <span
        className={cx(
          "absolute flex items-center gap-[1.036cqw] rounded-full bg-white pl-[4.145cqw] font-display text-[1.8135cqw] leading-[1.2] font-bold whitespace-nowrap text-medium",
          floatShadow,
        )}
        style={at(592, 488, 166, 56)}
      >
        <img src={asset("location.svg")} alt="" className="w-[3.109cqw]" />
        Top Places
      </span>
    </div>
  );
}

export function Hero() {
  return (
    <section className="shell flex flex-col items-center gap-8 py-8 md:gap-16 md:py-16 xl:flex-row-reverse xl:gap-0">
      <HeroCollage />
      <div className="flex w-full flex-col items-center text-center xl:min-w-0 xl:flex-1 xl:items-start xl:text-left">
        <p className="flex items-center gap-4 rounded-full bg-white px-8 py-4 shadow-[0_34px_37.5px_rgba(0,0,0,0.07),0_137px_68.5px_rgba(0,0,0,0.06)]">
          <span className="font-display text-[14px] leading-[1.2] font-bold text-secondary">Explore the world!</span>
          <img src={asset("work.svg")} alt="" width={24} height={24} className="size-6" />
        </p>
        <h1 className="mt-4 font-display text-[40px] leading-[1.2] font-bold text-black md:mt-[43px] md:text-[56px] xl:text-[69px]">
          Travel <span className="text-secondary">top destination</span>
          <br className="max-md:hidden" /> of the world
        </h1>
        <p className="mt-6 text-[16px] leading-[1.6] text-ink/50 md:mt-[43px] md:text-[18px]">
          We always make our customer happy by providing
          <br />
          as many choices as possible
        </p>
        <div className="mt-8 flex w-full flex-col gap-6 md:mt-[43px] md:w-auto md:flex-row md:items-start md:gap-4">
          <a
            href="#"
            className="flex justify-center rounded-full bg-primary px-8 py-6 font-display text-[14px] leading-[1.2] font-bold text-light shadow-[0_5px_5.5px_rgba(0,0,0,0.1),0_20px_10px_rgba(0,0,0,0.09),0_45px_13.5px_rgba(0,0,0,0.05)] transition-colors hover:bg-primary/90 md:py-4"
          >
            Get Started
          </a>
          <a
            href="#"
            className="flex items-center justify-center gap-2 rounded-full border border-light bg-white px-8 py-6 font-display text-[14px] leading-[1.2] font-bold text-dark transition-colors hover:border-ink/20 md:py-4"
          >
            <img src={asset("play-circle.svg")} alt="" width={24} height={24} className="size-6" />
            Watch Demo
          </a>
        </div>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- Partners */

/** The Booking.com wordmark is built from masked layers in the design; rendered at 32px tall and scaled. */
function BookingLogo() {
  const mask = `url("${asset("booking-mask.svg")}")`;
  const single = (src: string): CSSProperties => ({
    maskImage: mask,
    maskSize: "188.604px 32px",
    maskRepeat: "no-repeat",
    backgroundImage: `url("${src}")`,
  });
  const double = (src: string): CSSProperties => ({
    maskImage: `${mask}, url("${asset("booking-mask2.svg")}")`,
    maskSize: "188.604px 32px, 188.563px 31.33px",
    maskPosition: "0px 0px, 0px 0.63px",
    maskRepeat: "no-repeat",
    maskComposite: "intersect",
    backgroundImage: `url("${src}")`,
  });
  const layers = [
    single(asset("booking-p1.svg")),
    single(asset("booking-p2.svg")),
    single(asset("booking-p3.svg")),
    double(asset("booking-p4.svg")),
    double(asset("booking-p5.svg")),
    single(asset("booking-p6.svg")),
    single(asset("booking-p7.svg")),
  ];
  return (
    <span role="img" aria-label="Booking.com" className="relative block h-5 w-[117.877px] shrink-0 md:h-8 md:w-[188.604px]">
      <span className="absolute top-0 left-0 block h-8 w-[188.604px] origin-top-left scale-[0.625] md:scale-100">
        {layers.map((style, i) => (
          <span key={i} className="absolute inset-0 bg-size-[100%_100%] bg-no-repeat" style={style} />
        ))}
      </span>
    </span>
  );
}

export function Partners() {
  return (
    <section aria-label="Our partners" className="shell py-8 md:py-16">
      <div className="flex flex-col items-center gap-8 xl:flex-row xl:justify-between">
        <div className="flex w-full flex-wrap items-center justify-center gap-x-[27px] gap-y-8 min-[420px]:justify-between md:w-auto md:flex-nowrap md:justify-start xl:contents">
          <img src={asset("brand-tripadvisor.svg")} alt="Tripadvisor" className="h-5 w-auto md:h-8" />
          <img src={asset("brand-2.svg")} alt="Expedia" className="h-5 w-auto md:h-8" />
          <BookingLogo />
        </div>
        <div className="flex items-center gap-[26px] xl:contents">
          <img src={asset("brand-4.svg")} alt="Airbnb" className="h-5 w-auto md:h-8" />
          <img src={asset("brand-5.svg")} alt="Orbitz" className="h-5 w-auto md:h-8" />
        </div>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- Services */

const SERVICES = [
  { icon: "destination.png", title: "Best Tour Guide", text: "What looked like a small patch of purple grass, above five feet." },
  { icon: "booking.png", title: "Easy Booking", text: "Square, was moving across the sand in their direction." },
  { icon: "cloudy.png", title: "Weather Forecast", text: "What looked like a small patch of purple grass, above five feet." },
];

export function Services() {
  return (
    <section className="py-8 md:py-16">
      <div className="shell flex flex-col gap-8 md:gap-16 xl:flex-row xl:items-center xl:gap-0">
        <div className="flex flex-col gap-4 text-center xl:w-[444px] xl:shrink-0 xl:text-left">
          <Eyebrow>Services</Eyebrow>
          <SectionTitle>Our top value categories for you</SectionTitle>
        </div>
        {/* On desktop the cards run past the right edge of the window and scroll sideways, as in the design. */}
        <div className="no-scrollbar xl:-my-16 xl:mr-[calc((1184px-100vw)/2)] xl:min-w-0 xl:flex-1 xl:overflow-x-auto xl:py-16">
          <ul className="flex flex-col gap-4 md:flex-row xl:w-max xl:gap-[21px] xl:pr-8">
            {SERVICES.map((s, i) => (
              <li
                key={s.title}
                className={cx(
                  "flex flex-col items-center gap-8 rounded-[32px] bg-white p-8 text-center md:min-h-[443px] md:flex-1 md:gap-16 lg:p-16 xl:w-[350px] xl:flex-none",
                  i === 1 ? "shadow-[0_41px_44.5px_rgba(0,0,0,0.1)]" : "border border-ink/10",
                )}
              >
                <img src={asset(s.icon)} alt="" width={64} height={64} className="size-16 object-cover" />
                <div className="flex flex-col gap-8">
                  <h3 className="font-display text-[24px] leading-[1.2] font-bold text-ink md:text-[28px]">{s.title}</h3>
                  <p className="text-[18px] leading-[1.6] text-ink/50">{s.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ Destinations */

const DESTINATIONS = [
  { image: "dest-1.jpg", alt: "Boats on a beach seen from above", title: "Paradise Beach, Bantayan Island", price: "$550.16", place: "Rome, Italy", rating: "4.8" },
  { image: "dest-2.png", alt: "A lionfish swimming in blue water", title: "Ocean with full of Colors", price: "$20.99", place: "Maldives", rating: "4.5" },
  { image: "dest-3.jpg", alt: "Misty mountain ridges above the clouds", title: "Mountain View, Above the cloud", price: "$150.99", place: "United Arab Emeries", rating: "5.0" },
];

export function Destinations() {
  const track = useRef<HTMLUListElement>(null);
  const scroll = (dir: 1 | -1) => {
    const el = track.current;
    if (!el) return;
    const card = el.firstElementChild as HTMLElement | null;
    el.scrollBy({ left: dir * ((card?.offsetWidth ?? 300) + 32), behavior: "smooth" });
  };

  return (
    <section className="shell flex flex-col gap-8 py-8 md:gap-16 md:py-16">
      <div className="flex flex-col items-center gap-8 md:gap-16 xl:flex-row xl:gap-0">
        <div className="flex w-full flex-col gap-4 text-center xl:flex-1 xl:text-left">
          <Eyebrow>Top Destination</Eyebrow>
          <SectionTitle>Explore top destination</SectionTitle>
        </div>
        <div className="flex w-full justify-between md:w-auto md:gap-8">
          <ArrowButton direction="prev" label="Previous destinations" onClick={() => scroll(-1)} />
          <ArrowButton direction="next" label="Next destinations" onClick={() => scroll(1)} />
        </div>
      </div>

      <ul
        ref={track}
        className="no-scrollbar flex snap-x snap-mandatory flex-col gap-8 md:-mb-24 md:flex-row md:gap-[31px] md:overflow-x-auto md:pb-24 lg:mb-0 lg:overflow-visible lg:pb-0 xl:gap-8"
      >
        {DESTINATIONS.map((d) => (
          <li key={d.title} className="flex h-[575px] snap-start flex-col md:min-w-[250px] md:flex-1">
            <img
              src={asset(d.image)}
              alt={d.alt}
              className="min-h-0 w-full flex-1 rounded-t-[32px] bg-[#d9d9d9] object-cover"
            />
            <div className="flex flex-col gap-8 rounded-b-[32px] bg-white p-8 shadow-[0_32px_35.5px_rgba(0,0,0,0.05),0_128px_64px_rgba(0,0,0,0.04)] md:shadow-[0_24px_30px_rgba(0,0,0,0.06)] lg:shadow-[0_32px_35.5px_rgba(0,0,0,0.05),0_128px_64px_rgba(0,0,0,0.04)]">
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-2 font-display text-[23px] leading-[1.2] font-bold xl:flex-row xl:gap-0">
                  <p className="text-secondary xl:order-last xl:whitespace-nowrap">{d.price}</p>
                  <h3 className="text-ink xl:min-w-0 xl:flex-1">{d.title}</h3>
                </div>
                <p className="text-[18px] leading-[1.6] text-ink/75">{d.place}</p>
              </div>
              <p className="flex items-center gap-2 font-display text-[23px] leading-[1.2] font-bold text-orange">
                {d.rating}
                <img src={asset("star.svg")} alt="" width={24} height={24} className="size-6" />
                <span className="sr-only">out of 5</span>
              </p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* ------------------------------------------------------------ Travel point */

const STATS = [
  { value: "500+", label: "Holiday Package" },
  { value: "100", label: "Luxury Hotel" },
  { value: "7", label: "Premium Airlines" },
  { value: "2k+", label: "Happy Customer" },
];

export function TravelPoint() {
  return (
    <section className="relative py-8 md:py-16">
      <div className="flex flex-col gap-16 px-4 md:px-24 xl:flex-row xl:items-end xl:gap-0 xl:pr-[calc((100vw-1184px)/2)] xl:pl-0">
        {/* Desktop: the image bleeds to the left edge of the window. */}
        <img
          src={asset("travel-point.png")}
          alt="A smiling traveller with a backpack sitting on a suitcase, holding a passport and ticket"
          className="aspect-[871/697] w-full max-w-[871px] self-center object-cover xl:w-[min(871px,60.5vw)] xl:shrink-0 xl:self-auto"
        />
        <div className="flex flex-col gap-8 text-center md:gap-16 xl:min-w-0 xl:flex-1 xl:text-left">
          <div className="flex flex-col gap-8">
            <div className="flex flex-col gap-4">
              <Eyebrow>Travel Point</Eyebrow>
              <SectionTitle>We helping you find your dream location</SectionTitle>
            </div>
            <p className="text-[16px] leading-[1.6] text-ink/50 md:text-[18px]">
              Contrary to popular belief, Lorem Ipsum is not simply random text. It has roots in a piece of classical
              Latin literature from 45 BC.
            </p>
          </div>
          <dl className="grid grid-cols-1 gap-4 md:grid-cols-2 md:gap-8">
            {STATS.map((s) => (
              <div
                key={s.label}
                className="flex flex-col-reverse items-center gap-4 rounded-[32px] border border-ink/10 bg-white p-8"
              >
                <dt className="text-[18px] leading-[1.6] whitespace-nowrap text-ink">{s.label}</dt>
                <dd className="font-display text-[35px] leading-[1.2] font-bold text-orange">{s.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
      <img
        src={asset("discount-card.png")}
        alt=""
        aria-hidden
        className="pointer-events-none absolute top-[289px] right-0 hidden h-[353px] w-[277px] min-[1400px]:block"
      />
    </section>
  );
}

/* ------------------------------------------------------------ Key features */

const FEATURES = [
  { icon: "location-white.svg", bg: "bg-orange", title: "We offer best services", text: "Lorem Ipsum is not simply random text", inset: 26 },
  { icon: "calendar.svg", bg: "bg-yellow", title: "Schedule your trip", text: "It has roots in a piece of classical", inset: 24 },
  { icon: "ticket.svg", bg: "bg-secondary", title: "Get discounted coupons", text: "Lorem Ipsum is not simply random text", inset: 26 },
];

export function KeyFeatures() {
  return (
    <section className="py-8 md:py-16">
      <div className="flex flex-col items-center gap-16 px-12 md:gap-[70px] md:px-24 xl:flex-row-reverse xl:items-start xl:pr-0 xl:pl-[calc((100vw-1184px)/2)]">
        {/* Desktop: the image bleeds to the right edge of the window. */}
        <img
          src={asset("features-bg.png")}
          alt="A black church on a hillside and a surfer riding a wave, framed in arches"
          className="aspect-[693/869] w-full max-w-[350px] object-cover md:max-w-[693px] xl:w-[min(693px,48vw)] xl:shrink-0"
        />
        <div className="flex w-full flex-col gap-8 md:gap-16 xl:min-w-0 xl:flex-1">
          <div className="flex flex-col gap-8 text-center xl:text-left">
            <div className="flex flex-col gap-4">
              <Eyebrow>Key features</Eyebrow>
              <SectionTitle>We offer best services</SectionTitle>
            </div>
            <p className="text-[16px] leading-[1.6] text-ink/50 md:text-[18px]">
              Contrary to popular belief, Lorem Ipsum is not simply random text. It has roots in a piece of classical
              Latin literature from 45 BC.
            </p>
          </div>
          <ul className="flex flex-col gap-2 md:gap-0">
            {FEATURES.map((f, i) => (
              <li
                key={f.title}
                className={cx(
                  "flex flex-col gap-8 rounded-[32px] bg-white p-8 md:flex-row md:items-center",
                  i === 1 && "border border-ink/10",
                )}
              >
                <span className={cx("relative size-[100px] shrink-0 rounded-[32px]", f.bg)}>
                  <img
                    src={asset(f.icon)}
                    alt=""
                    width={48}
                    height={48}
                    className="absolute size-12"
                    style={{ left: f.inset, top: f.inset }}
                  />
                </span>
                <div className="flex min-w-0 flex-col gap-2">
                  <h3 className="font-display text-[23px] leading-[1.2] font-bold text-ink">{f.title}</h3>
                  <p className="text-[18px] leading-[1.6] text-ink/50">{f.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ Testimonials */

export function Testimonials() {
  return (
    <section className="relative py-8 md:py-16 xl:py-0">
      <div
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-[calc(50%-163px)] -z-10 hidden w-[2506px] -translate-x-1/2 -translate-y-1/2 -rotate-[9.37deg] opacity-10 md:block"
      >
        <img src={asset("testimonial-bg.svg")} alt="" className="block w-full max-w-none" />
      </div>

      <div className="shell flex flex-col items-center gap-16 md:flex-row md:gap-14">
        <div className="hidden md:block">
          <ArrowButton direction="prev" label="Previous testimonial" />
        </div>

        <figure className="flex w-full min-w-0 flex-col items-center gap-16 text-center md:flex-1 md:gap-14">
          <div className="flex w-full flex-col gap-4">
            <Eyebrow>Testimonials</Eyebrow>
            <SectionTitle>Trust our clients</SectionTitle>
          </div>
          <img src={asset("avatar.png")} alt="Mark Smith" width={128} height={128} className="size-32 rounded-full" />
          <figcaption className="flex flex-col items-center gap-8">
            <p className="font-display leading-[1.2] font-bold">
              <span className="text-[28px] text-orange">Mark Smith </span>
              <span className="text-[23px] text-ink/75">/ Travel Enthusiast</span>
            </p>
            <p className="flex gap-4" role="img" aria-label="Rated 5 out of 5">
              {Array.from({ length: 5 }, (_, i) => (
                <img key={i} src={asset("star-lg.svg")} alt="" width={32} height={32} className="size-8" />
              ))}
            </p>
          </figcaption>
          <blockquote className="font-display text-[18px] leading-[1.6] font-normal text-ink/75 md:text-[23px]">
            Contrary to popular belief, Lorem Ipsum is not simply random text. It has roots in a piece of classical
            Latin literature from 45 BC.
          </blockquote>
          <img src={asset("dots.svg")} alt="" width={120} height={24} className="h-6 w-[120px]" />
        </figure>

        <div className="flex w-full justify-between md:w-auto">
          <div className="md:hidden">
            <ArrowButton direction="prev" label="Previous testimonial" />
          </div>
          <ArrowButton direction="next" label="Next testimonial" />
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------- Newsletter */

export function Newsletter() {
  const [sent, setSent] = useState(false);
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSent(true);
  };

  return (
    <section className="shell relative pt-8 md:pt-16 xl:pt-[177px]">
      <div className="relative rounded-[32px] bg-yellow/8 px-8 py-16 md:px-16 md:py-32">
        <img
          src={asset("graphic-elements.svg")}
          alt=""
          aria-hidden
          className="pointer-events-none absolute -top-[67px] -left-[35px] hidden h-[176.35px] w-[183.86px] md:block"
        />
        <div className="relative flex flex-col gap-16">
          <div className="flex flex-col gap-8 text-center">
            <Eyebrow>subscribe to our newsletter</Eyebrow>
            <h2 className="font-display text-[32px] leading-[1.2] font-bold text-ink md:text-[40px] xl:text-[55px]">
              Prepare yourself &amp; let’s explore the beauty of the world
            </h2>
          </div>
          <form onSubmit={submit} className="flex flex-col gap-8 md:flex-row xl:gap-16">
            <label className="flex min-w-0 flex-1 items-center gap-4 rounded-2xl bg-white px-8 py-6 focus-within:ring-2 focus-within:ring-primary md:rounded-[32px] md:p-8">
              <img src={asset("message.svg")} alt="" width={32} height={32} className="size-6 md:size-8" />
              <span className="sr-only">Your Email</span>
              <input
                type="email"
                required
                placeholder="Your Email"
                className="min-w-0 flex-1 bg-transparent font-display text-[14px] leading-[1.2] font-bold text-ink outline-none placeholder:text-ink/75 md:text-[23px]"
              />
            </label>
            <button
              type="submit"
              className="flex cursor-pointer items-center justify-center rounded-2xl bg-primary px-16 py-6 font-display text-[16px] leading-[1.2] font-bold text-white transition-colors hover:bg-primary/90 md:rounded-[32px] md:py-8 md:text-[23px]"
            >
              {sent ? "Subscribed!" : "Subscribe"}
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ Footer */

type FooterCol = { title: string; phoneTitle: string; links: string[]; extra?: string };

const FOOTER_COLUMNS: FooterCol[] = [
  { title: "Company", phoneTitle: "Company", links: ["About", "Career", "Mobile"] },
  { title: "Contact", phoneTitle: "Contact Us", links: ["Why Travlog?", "Partner with us", "FAQ’s", "Blog"] },
  {
    title: "Meet Us",
    phoneTitle: "Meet Us",
    links: ["+00 92 1234 56789", "info@travlog.com", "205. R Street, New York"],
    extra: "BD23200",
  },
];

const SOCIALS = [
  { icon: "social-1.svg", label: "Facebook" },
  { icon: "social-2.svg", label: "Twitter" },
  { icon: "social-3.svg", label: "Instagram" },
];

/** A link column; on phones its heading becomes an accordion toggle, as in the phone frame. */
function FooterColumn({ col }: { col: FooterCol }) {
  const [open, setOpen] = useState(false);
  const id = `footer-${col.title.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className="flex flex-col gap-8 md:min-w-0 md:flex-1">
      <h3 className="font-display text-[23px] leading-[1.2] font-bold text-ink">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((v) => !v)}
          className="flex w-full cursor-pointer items-start gap-8 text-left md:hidden"
        >
          <span className="flex-1">{col.phoneTitle}</span>
          <img
            src={asset("arrow-circle-down.svg")}
            alt=""
            width={24}
            height={24}
            className={cx("size-6 transition-transform", open && "rotate-180")}
          />
        </button>
        <span className="hidden md:inline">{col.title}</span>
      </h3>
      <ul
        id={id}
        className={cx("flex-col gap-8 text-[18px] leading-[1.6] text-ink/75 md:flex", open ? "flex" : "hidden")}
      >
        {col.links.map((l, i) => (
          <li key={l}>
            {col.extra && i === col.links.length - 1 ? (
              <span className="flex flex-col gap-2">
                <span>{l}</span>
                <span>{col.extra}</span>
              </span>
            ) : (
              <a href="#" className="hover:text-ink">
                {l}
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Footer() {
  return (
    <footer className="relative">
      <img
        src={asset("objects-rings.svg")}
        alt=""
        aria-hidden
        className="pointer-events-none absolute -top-[75px] -right-[250px] hidden h-[351.949px] w-[332px] md:block xl:-top-[192px] xl:-right-[220px]"
      />
      <div className="shell relative flex flex-col gap-16 py-8 md:py-16 xl:flex-row">
        <div className="flex flex-col gap-8 md:gap-16 xl:min-w-0 xl:flex-1">
          <div className="flex flex-col gap-8">
            <Logo />
            <p className="font-display text-[16px] leading-[1.6] font-normal text-ink/50 md:text-[23px]">
              Contrary to popular belief, Lorem Ipsum is not simply random text. It has roots in a piece of classical
              Latin literature from 45 BC.
            </p>
          </div>
          <ul className="flex gap-8">
            {SOCIALS.map((s) => (
              <li key={s.label}>
                <a href="#" aria-label={s.label} className="block transition-opacity hover:opacity-80">
                  <img src={asset(s.icon)} alt="" width={32} height={32} className="size-8" />
                </a>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-col gap-16 md:flex-row md:gap-8 xl:min-w-0 xl:flex-1">
          {FOOTER_COLUMNS.map((c) => (
            <FooterColumn key={c.title} col={c} />
          ))}
        </div>
      </div>
    </footer>
  );
}
