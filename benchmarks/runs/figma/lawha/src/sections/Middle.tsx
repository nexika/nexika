import { useRef } from "react";
import { ArrowButton, asset, column, Eyebrow, gutter, SectionTitle } from "./ui";

const logo = "h-5 w-auto md:h-8";

export function Partners() {
  return (
    <div className={`relative ${gutter}`}>
      {/* Decorations: the yellow glow on the right and the orange triangles on the left (tablet and up). */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 -top-[600px] hidden h-[1400px] overflow-hidden md:block">
        <div className="absolute top-[595px] left-[calc(50%+434px)] size-[406px] rounded-full bg-yellow/50 blur-[200px] xl:top-[493px] xl:left-[calc(50%+631px)] xl:size-[500px] xl:blur-[250px]" />
        <img
          src={asset("deco-triangles.svg")}
          alt=""
          className="absolute top-[383px] left-[37px] w-[65px] xl:top-[488px]"
        />
      </div>
      <section
        aria-label="Our partners"
        className={`${column} relative flex flex-col items-center gap-8 py-8 md:mt-8 md:py-16 xl:mt-0 xl:flex-row xl:justify-between`}
      >
        <div className="flex w-full gap-[27px] md:w-auto xl:contents">
          <img src={asset("logo-tripadvisor.svg")} alt="Tripadvisor" className={logo} width={212} height={32} />
          <img src={asset("logo-expedia.svg")} alt="Expedia" className={logo} width={113} height={32} />
          <img src={asset("logo-booking.svg")} alt="Booking.com" className={logo} width={189} height={32} />
        </div>
        <div className="flex gap-[26px] xl:contents">
          <img src={asset("logo-airbnb.svg")} alt="Airbnb" className={logo} width={103} height={32} />
          <img src={asset("logo-orbitz.svg")} alt="Orbitz" className={logo} width={174} height={32} />
        </div>
      </section>
    </div>
  );
}

const services = [
  {
    icon: "icon-tour-guide.png",
    title: "Best Tour Guide",
    text: "What looked like a small patch of purple grass, above five feet.",
    style: "ring-1 ring-inset ring-grey-scale-black-10",
  },
  {
    icon: "icon-booking.png",
    title: "Easy Booking",
    text: "Square, was moving across the sand in their direction.",
    style: "shadow-[0_41px_89px_rgba(0,0,0,0.1)]",
  },
  {
    icon: "icon-weather.png",
    title: "Weather Forecast",
    text: "What looked like a small patch of purple grass, above five feet.",
    style: "ring-1 ring-inset ring-grey-scale-black-10",
  },
];

export function Services() {
  return (
    <div className={`relative ${gutter}`}>
      <section
        aria-labelledby="services-title"
        className={`${column} flex flex-col items-start gap-8 py-8 md:mt-[5px] md:gap-16 md:py-16 xl:ms-[calc(50%-592px)] xl:me-0 xl:max-w-none xl:w-auto xl:flex-row xl:items-center xl:gap-0 xl:py-0`}
      >
        <div className="flex w-full flex-col items-center gap-4 xl:w-[444px] xl:flex-none xl:items-start">
          <Eyebrow className="text-center xl:text-start">Services</Eyebrow>
          <SectionTitle id="services-title" className="text-center xl:text-start">
            Our top value categories for you
          </SectionTitle>
        </div>
        {/* On desktops the third card runs past the screen edge, as in the design: the row scrolls sideways. */}
        <div
          role="region"
          aria-label="Services"
          tabIndex={0}
          className="w-full focus-visible:outline-2 focus-visible:outline-primary xl:min-w-0 xl:flex-1 xl:overflow-x-auto xl:py-16 xl:[scrollbar-width:none]"
        >
          <ul className="flex flex-col gap-4 md:flex-row xl:w-[1092px] xl:gap-[21px]">
            {services.map((s) => (
              <li
                key={s.title}
                className={`flex flex-col items-center gap-8 rounded-[32px] bg-white p-8 md:h-[443px] md:min-w-0 md:flex-1 md:gap-16 md:p-8 lg:p-16 ${s.style}`}
              >
                <img src={asset(s.icon)} alt="" width={64} height={64} className="size-16" />
                <div className="flex w-full flex-col items-center gap-8 text-center">
                  <h3 className="text-[24px] leading-[28.8px] font-bold text-grey-scale-black md:text-[28px] md:leading-[33.6px]">
                    {s.title}
                  </h3>
                  <p className="font-inter text-[18px] leading-[28.8px] text-grey-scale-black-50">{s.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}

const destinations = [
  {
    photo: "paradise-beach.jpg",
    alt: "Boats on a sandy beach seen from above",
    price: "$550.16",
    title: "Paradise Beach, Bantayan Island",
    place: "Rome, Italy",
    rating: "4.8",
    radius: "rounded-t-[32px]",
  },
  {
    photo: "ocean-colors.jpg",
    alt: "A lionfish swimming in blue water",
    price: "$20.99",
    title: "Ocean with full of Colors",
    place: "Maldives",
    rating: "4.5",
    radius: "rounded-t-[24px]",
  },
  {
    photo: "mountain-view.jpg",
    alt: "Mountain ridges above a sea of clouds",
    price: "$150.99",
    title: "Mountain View, Above the cloud",
    place: "United Arab Emeries ",
    rating: "5.0",
    radius: "rounded-t-[32px]",
  },
];

const infoShadow =
  "shadow-[0_32px_71px_rgba(0,0,0,0.05),0_128px_128px_rgba(0,0,0,0.04),0_288px_173px_rgba(0,0,0,0.03),0_513px_205px_rgba(0,0,0,0.01)]";

export function Destinations() {
  const list = useRef<HTMLUListElement>(null);
  const scroll = (dir: 1 | -1) => {
    const el = list.current;
    if (!el) return;
    const card = el.firstElementChild as HTMLElement | null;
    el.scrollBy({ left: dir * (card?.offsetWidth ?? 300), behavior: "smooth" });
  };
  return (
    <div className={gutter}>
      <section
        aria-labelledby="destinations-title"
        className={`${column} flex flex-col gap-8 py-8 md:mt-[5px] md:gap-[67px] md:py-16 xl:mt-0 xl:gap-16`}
      >
        <div className="flex w-full flex-col items-center gap-8 md:gap-16 xl:flex-row xl:gap-0">
          <div className="flex w-full flex-col gap-4 xl:flex-1">
            <Eyebrow className="text-center xl:text-start">Top Destination</Eyebrow>
            <SectionTitle id="destinations-title" className="text-center xl:text-start">
              Explore top destination
            </SectionTitle>
          </div>
          <div className="flex w-full justify-between md:w-auto md:justify-start md:gap-8">
            <ArrowButton direction="prev" label="Previous destinations" onClick={() => scroll(-1)} />
            <ArrowButton direction="next" label="Next destinations" onClick={() => scroll(1)} />
          </div>
        </div>
        <ul ref={list} className="flex flex-col gap-8 md:flex-row md:gap-[31px] xl:gap-8">
          {destinations.map((d) => (
            <li key={d.title} className="flex h-[575px] w-full flex-col md:min-w-0 md:flex-1">
              <img
                src={asset(d.photo)}
                alt={d.alt}
                className={`min-h-0 w-full flex-1 object-cover ${d.radius}`}
              />
              <div className={`flex flex-col gap-8 rounded-b-[32px] bg-white p-8 ${infoShadow}`}>
                <div className="flex flex-col gap-4">
                  <div className="flex flex-col gap-2 xl:flex-row xl:gap-0">
                    <h3 className="text-[23px] leading-[27.6px] font-bold text-grey-scale-black xl:flex-1">
                      {d.title}
                    </h3>
                    <p className="order-first text-[23px] leading-[27.6px] font-bold text-secondary-text xl:order-none">
                      {d.price}
                    </p>
                  </div>
                  <p className="font-inter text-[18px] leading-[28.8px] text-grey-scale-black-75">{d.place}</p>
                </div>
                <p className="flex items-center gap-2">
                  <span className="text-[23px] leading-[27.6px] font-bold text-orange">{d.rating}</span>
                  <img src={asset("star-1.svg")} alt="out of 5 stars" width={24} height={24} className="size-6" />
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
