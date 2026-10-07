import { asset, column, gutter, Logo } from "./ui";

const navLinks = ["Home", "Discover", "Special Deals", "Contact"];

export function Header({ menuOpen, onToggleMenu }: { menuOpen: boolean; onToggleMenu: () => void }) {
  return (
    <header className={`relative z-20 ${gutter}`}>
      {/* Tablet only: the soft orange glow in the top corner. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 hidden h-[900px] overflow-hidden md:block xl:hidden">
        <div className="absolute -top-[223px] -left-[356px] size-[500px] rounded-full bg-orange/50 blur-[250px]" />
      </div>
      <div className={`${column} relative flex items-center justify-between py-8`}>
        <a href="#" aria-label="Travlog home" className="rounded-lg focus-visible:outline-2 focus-visible:outline-primary">
          <Logo />
        </a>

        <nav aria-label="Main" className="hidden xl:block">
          <ul className="flex gap-16">
            {navLinks.map((link, i) => (
              <li key={link}>
                <a
                  href="#"
                  aria-current={i === 0 ? "page" : undefined}
                  className={`-mx-2 -my-3.5 block px-2 py-3.5 text-[14px] leading-[16.8px] font-bold ${
                    i === 0 ? "text-dark" : "text-grey-scale-black-50"
                  } hover:text-dark`}
                >
                  {link}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="hidden md:flex">
          <a href="#" className="rounded-full bg-white px-8 py-4 text-[14px] leading-[16.8px] font-bold text-dark">
            Log In
          </a>
          <a href="#" className="rounded-full bg-primary px-8 py-4 text-[14px] leading-[16.8px] font-bold text-light">
            Sign Up
          </a>
        </div>

        <button
          type="button"
          aria-expanded={menuOpen}
          aria-controls="mobile-menu"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          onClick={onToggleMenu}
          className="size-12 shrink-0 rounded-xl md:order-first xl:hidden focus-visible:outline-2 focus-visible:outline-primary"
        >
          <img src={asset("menu.svg")} alt="" width={48} height={48} className="size-12" />
        </button>

        {menuOpen && (
          <div
            id="mobile-menu"
            className="absolute inset-x-0 top-full z-30 rounded-[32px] bg-white p-8 shadow-[0_34px_75px_rgba(0,0,0,0.12)] xl:hidden"
          >
            <ul className="flex flex-col gap-2">
              {navLinks.map((link) => (
                <li key={link}>
                  <a href="#" className="block py-3 text-[18px] font-bold text-dark">
                    {link}
                  </a>
                </li>
              ))}
            </ul>
            <div className="mt-6 flex flex-col gap-4 md:hidden">
              <a href="#" className="rounded-full px-8 py-4 text-center text-[14px] font-bold text-dark ring-1 ring-inset ring-light">
                Log In
              </a>
              <a href="#" className="rounded-full bg-primary px-8 py-4 text-center text-[14px] font-bold text-light">
                Sign Up
              </a>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}

const floatShadow =
  "shadow-[0_9.75px_9.75px_rgba(0,0,0,0.09),0_22px_13px_rgba(0,0,0,0.05)] md:shadow-[0_19px_19px_rgba(0,0,0,0.09),0_43px_26px_rgba(0,0,0,0.05),0_77px_31px_rgba(0,0,0,0.01)]";

/** The photo collage. Every position is a share of the 772 x 713 design box, so it scales with the screen. */
function Collage() {
  return (
    <div className="relative aspect-[772/713] w-full max-w-[396px] shrink-0 md:max-w-[772px] xl:order-2 xl:w-[772px]">
      <img
        src={asset("hero-map.svg")}
        alt=""
        className="absolute top-0 left-0 w-full"
        width={772}
        height={287}
      />
      <img
        src={asset("santorini-stairs.jpg")}
        alt="White stairs leading down to the sea in Santorini"
        className="absolute top-[10.52%] left-[11.79%] h-[42.08%] w-[35.23%] rounded-2xl object-cover md:rounded-[32px]"
      />
      <img
        src={asset("hiker-mountains.jpg")}
        alt="A hiker resting on a rock in front of snowy mountains"
        className="absolute top-[57.08%] left-[11.79%] h-[42.08%] w-[35.23%] rounded-2xl object-cover md:rounded-[32px]"
      />
      <img
        src={asset("city-backpacker.jpg")}
        alt="A traveller with a backpack taking a photo in a city"
        className="absolute top-[26.79%] left-[51.04%] h-[56.1%] w-[35.23%] rounded-2xl object-cover md:rounded-[32px]"
      />
      <div
        aria-hidden="true"
        className={`absolute top-[47.83%] left-[7.25%] grid size-8 place-items-center rounded-full bg-secondary md:size-16 ${floatShadow}`}
      >
        <img src={asset("send-1.svg")} alt="" className="size-4 md:size-8" />
      </div>
      <div
        aria-hidden="true"
        className={`absolute top-[91.02%] left-[61.4%] grid size-8 place-items-center rounded-full bg-orange md:size-16 ${floatShadow}`}
      >
        <img src={asset("add-user-1.svg")} alt="" className="size-4 md:size-8" />
      </div>
      <div
        className="absolute top-[68.44%] left-[76.68%] flex items-center gap-1 rounded-full bg-white px-4 py-2 whitespace-nowrap shadow-[0_22px_13px_rgba(0,0,0,0.05),0_39.5px_16px_rgba(0,0,0,0.01)] md:gap-2 md:px-8 md:py-4 md:shadow-[0_43px_26px_rgba(0,0,0,0.05),0_77px_31px_rgba(0,0,0,0.01)]"
      >
        <img src={asset("location-1.svg")} alt="" className="size-3 md:size-6" />
        <span className="text-[7.2px] leading-[8.6px] font-bold text-medium md:text-[14px] md:leading-[16.8px]">
          Top Places
        </span>
      </div>
    </div>
  );
}

const pillShadow =
  "shadow-[0_34px_75px_rgba(0,0,0,0.07),0_137px_137px_rgba(0,0,0,0.06),0_308px_185px_rgba(0,0,0,0.04)]";

export function Hero() {
  return (
    <div className={`relative ${gutter}`}>
      <section
        aria-labelledby="hero-title"
        className={`${column} flex flex-col items-center gap-8 py-8 md:gap-16 md:py-16 xl:flex-row xl:gap-0`}
      >
        <Collage />
        <div className="flex w-full flex-col items-center gap-8 md:gap-[43px] xl:flex-1 xl:items-start">
          <div className="flex flex-col items-center gap-6 md:contents">
            <div className="flex flex-col items-center gap-4 md:contents">
              <p className={`flex items-center gap-4 rounded-full bg-white px-8 py-4 ${pillShadow}`}>
                <span className="text-[14px] leading-[16.8px] font-bold text-secondary-text">Explore the world!</span>
                <img src={asset("work-1.svg")} alt="" width={24} height={24} className="size-6" />
              </p>
              <h1
                id="hero-title"
                className="w-full max-w-[398px] text-center text-[40px] leading-[48px] font-bold tracking-[-0.02em] text-[#000] md:max-w-none md:text-[56px] md:leading-[67.2px] xl:text-start xl:text-[69px] xl:leading-[82.8px]"
              >
                Travel <span className="text-secondary-text">top destination</span>
                <br className="hidden md:inline" /> of the world
              </h1>
            </div>
            <p className="w-full max-w-[398px] text-center font-inter text-[16px] leading-[25.6px] text-grey-scale-black-50 md:max-w-none md:text-[18px] md:leading-[28.8px] xl:text-start">
              We always make our customer happy by providing
              <br />
              as many choices as possible
            </p>
          </div>
          <div className="flex w-full flex-col gap-6 md:w-auto md:flex-row md:gap-4">
            <a
              href="#"
              className="flex justify-center rounded-full bg-primary px-8 py-6 text-[14px] leading-[16.8px] font-bold text-light shadow-[0_5px_11px_rgba(0,0,0,0.1),0_20px_20px_rgba(0,0,0,0.09),0_45px_27px_rgba(0,0,0,0.05),0_81px_32px_rgba(0,0,0,0.01)] md:justify-start md:py-4 md:self-start"
            >
              Get Started
            </a>
            <a
              href="#"
              className="flex items-center justify-center gap-2 rounded-full bg-white px-8 py-6 text-[14px] leading-[16.8px] font-bold text-dark ring-1 ring-inset ring-light md:justify-start md:py-4"
            >
              <img src={asset("play-circle-5-1.svg")} alt="" width={24} height={24} className="size-6" />
              Watch Demo
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
