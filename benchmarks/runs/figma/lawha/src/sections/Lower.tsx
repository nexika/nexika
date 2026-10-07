import { useState } from "react";
import { ArrowButton, asset, column, Eyebrow, gutter, SectionTitle } from "./ui";

const bodyText =
  "w-full font-inter text-[16px] leading-[25.6px] text-grey-scale-black-50 text-center md:text-[18px] md:leading-[28.8px] xl:text-start";

const stats = [
  [
    { value: "500+", label: "Holiday Package" },
    { value: "100", label: "Luxury Hotel" },
  ],
  [
    { value: "7", label: "Premium Airlines" },
    { value: "2k+", label: "Happy Customer" },
  ],
];

export function TravelPoint() {
  return (
    <div className={`relative ${gutter}`}>
      {/* Desktop only: the yellow ticket badge on the right edge. */}
      <img
        src={asset("ticket-badge.png")}
        alt=""
        aria-hidden="true"
        className="pointer-events-none absolute top-[289px] right-0 hidden w-[277px] xl:block"
      />
      <section
        aria-labelledby="travel-point-title"
        className={`${column} flex flex-col items-start justify-end gap-16 py-8 md:px-8 md:py-16 xl:ms-0 xl:me-[calc(50%-592px)] xl:w-auto xl:max-w-none xl:flex-row xl:items-end xl:gap-0 xl:px-0`}
      >
        <img
          src={asset("traveler-suitcase.png")}
          alt="A smiling traveller with a backpack sitting on a suitcase, with a “Discounted Price” label"
          width={871}
          height={697}
          className="h-auto w-full max-w-[398px] md:w-[min(871px,calc(100vw-96px))] md:max-w-none xl:w-[871px] xl:shrink-0"
        />
        <div className="flex w-full flex-col gap-8 md:gap-16 xl:flex-1">
          <div className="flex w-full flex-col gap-8">
            <div className="flex w-full flex-col gap-4">
              <Eyebrow className="text-center xl:text-start">Travel Point</Eyebrow>
              <SectionTitle id="travel-point-title" className="text-center xl:text-start">
                We helping you find your dream location
              </SectionTitle>
            </div>
            <p className={bodyText}>
              Contrary to popular belief, Lorem Ipsum is not simply random text. It has roots in a piece of classical
              Latin literature from 45 BC.
            </p>
          </div>
          <ul className="flex w-full flex-col gap-4 md:gap-8">
            {stats.map((row, i) => (
              <li key={i} className="flex w-full flex-col gap-4 md:flex-row md:gap-8">
                {row.map((s) => (
                  <p
                    key={s.label}
                    className="flex flex-col items-center gap-4 rounded-[32px] bg-white p-8 ring-1 ring-inset ring-grey-scale-black-10 md:flex-1"
                  >
                    <span className="text-[35px] leading-[42px] font-bold text-orange">{s.value}</span>
                    <span className="font-inter text-[18px] leading-[28.8px] whitespace-nowrap text-grey-scale-black">{s.label}</span>
                  </p>
                ))}
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}

const features = [
  {
    icon: "location-2.svg",
    bg: "bg-orange",
    title: "We offer best services",
    text: "Lorem Ipsum is not simply random text",
    ring: "",
  },
  {
    icon: "calendar-1.svg",
    bg: "bg-yellow",
    title: "Schedule your trip",
    text: "It has roots in a piece of classical",
    ring: "ring-1 ring-inset ring-grey-scale-black-10",
  },
  {
    icon: "ticket-1.svg",
    bg: "bg-secondary",
    title: "Get discounted coupons",
    text: "Lorem Ipsum is not simply random text",
    ring: "",
  },
];

export function Features() {
  return (
    <div className={gutter}>
      <section
        aria-labelledby="features-title"
        className={`${column} flex flex-col items-center gap-16 p-8 md:gap-[70px] md:px-8 md:py-16 xl:ms-[calc(50%-592px)] xl:me-0 xl:w-auto xl:max-w-none xl:flex-row xl:items-start xl:px-0`}
      >
        <img
          src={asset("church-and-surfer.png")}
          alt="A black church in a golden field and a surfer in the waves, with a “Paradise on Earth” label"
          width={693}
          height={869}
          className="h-auto w-[350px] max-w-none shrink-0 md:w-[min(693px,calc(100vw-64px))] xl:order-2 xl:w-[693px]"
        />
        <div className="flex w-full flex-col gap-8 md:gap-16 xl:flex-1">
          <div className="flex w-full flex-col gap-8">
            <div className="flex w-full flex-col gap-4">
              <Eyebrow className="text-center xl:text-start">Key features</Eyebrow>
              <SectionTitle id="features-title" className="text-center xl:text-start">
                We offer best services
              </SectionTitle>
            </div>
            <p className={bodyText}>
              Contrary to popular belief, Lorem Ipsum is not simply random text. It has roots in a piece of classical
              Latin literature from 45 BC.
            </p>
          </div>
          <ul className="flex w-full flex-col items-center gap-2 md:items-start md:gap-0">
            {features.map((f) => (
              <li
                key={f.title}
                className={`flex w-full flex-col items-start justify-center gap-8 rounded-[32px] bg-white p-8 md:flex-row md:items-center md:justify-start ${f.ring}`}
              >
                <span className={`grid size-[100px] shrink-0 place-items-center rounded-[32px] ${f.bg}`}>
                  <img src={asset(f.icon)} alt="" width={48} height={48} className="size-12" />
                </span>
                <div className="flex w-full flex-col gap-2 md:flex-1">
                  <h3 className="text-[23px] leading-[27.6px] font-bold text-grey-scale-black">{f.title}</h3>
                  <p className="font-inter text-[18px] leading-[28.8px] text-grey-scale-black-50">{f.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}

export function Testimonials() {
  const [active, setActive] = useState(1);
  const total = 3;
  return (
    <div className={`relative ${gutter} md:-mt-2 xl:mt-3`}>
      {/* The pale purple-to-pink wave behind the testimonials (tablet and up). */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 -top-[370px] hidden h-[1353px] overflow-hidden md:block">
        <div
          className="absolute top-[90px] left-[calc(50%-1321px)] h-[1256px] w-[2380px] bg-no-repeat xl:left-[calc(50%-1353px)]"
          style={{ backgroundImage: `url(${asset("wave-faded.svg")})` }}
        />
      </div>
      <section
        aria-labelledby="testimonials-title"
        aria-roledescription="carousel"
        className={`${column} relative flex flex-col items-center gap-16 py-8 md:flex-row md:gap-14 md:py-16 xl:py-0`}
      >
        <div className="flex w-full flex-col items-center gap-16 md:flex-1 md:gap-14">
          <div className="flex w-full flex-col items-center gap-4 text-center">
            <Eyebrow>Testimonials</Eyebrow>
            <SectionTitle id="testimonials-title">Trust our clients</SectionTitle>
          </div>
          <img
            src={asset("mark-smith.jpg")}
            alt="Mark Smith wearing a virtual reality headset"
            width={128}
            height={128}
            className="size-32 rounded-full object-cover"
          />
          <figure className="contents">
            <figcaption className="flex w-full flex-col items-center gap-8">
              <p className="text-center text-[28px] leading-[33.6px] font-bold text-[#e64a19]">
                Mark Smith{" "}
                <span className="text-[23px] leading-[27.6px] text-grey-scale-black-75">/ Travel Enthusiast</span>
              </p>
              <p className="flex justify-center gap-4" role="img" aria-label="Rated 5 out of 5">
                {["star-2", "star-3", "star-4", "star-5", "star-6"].map((s) => (
                  <img key={s} src={asset(`${s}.svg`)} alt="" width={32} height={32} className="size-8" />
                ))}
              </p>
            </figcaption>
            <blockquote className="w-full text-center text-[18px] leading-[28.8px] font-[450] text-grey-scale-black-75 md:text-[23px] md:leading-[36.8px]">
              Contrary to popular belief, Lorem Ipsum is not simply random text. It has roots in a piece of classical
              Latin literature from 45 BC.
            </blockquote>
          </figure>
          <div className="flex gap-6" aria-label={`Testimonial ${active + 1} of ${total}`} role="group">
            {Array.from({ length: total }, (_, i) => (
              <span
                key={i}
                aria-hidden="true"
                className={`size-6 rounded-full ${i === active ? "bg-secondary" : "bg-grey-scale-black-5"}`}
              />
            ))}
          </div>
        </div>
        <div className="flex w-full justify-between md:contents">
          <ArrowButton
            direction="prev"
            label="Previous testimonial"
            onClick={() => setActive((a) => (a + total - 1) % total)}
            className="md:order-first"
          />
          <ArrowButton
            direction="next"
            label="Next testimonial"
            onClick={() => setActive((a) => (a + 1) % total)}
            className="md:order-last"
          />
        </div>
      </section>
    </div>
  );
}
