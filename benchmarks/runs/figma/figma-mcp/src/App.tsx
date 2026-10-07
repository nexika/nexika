import { asset } from "./components/ui";
import {
  Destinations,
  Footer,
  Header,
  Hero,
  KeyFeatures,
  Newsletter,
  Partners,
  Services,
  Testimonials,
  TravelPoint,
} from "./components/sections";

/** Blurred colour glows and small graphics that sit behind the content, placed as in each frame. */
function Decorations() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 hidden md:block">
      {/* Orange glow, top left (tablet). */}
      <img
        src={asset("ellipse-tl.svg")}
        alt=""
        className="absolute top-[-723px] left-[-856px] size-[1500px] max-w-none xl:hidden"
      />
      {/* Yellow glow on the right edge: beside the partner logos on tablet, the hero on desktop. */}
      <img
        src={asset("ellipse.svg")}
        alt=""
        className="absolute top-[1072px] right-[-734px] size-[1218px] max-w-none xl:top-[347px] xl:right-[-911px] xl:size-[1500px]"
      />
      {/* Orange triangles on the left edge. */}
      <div className="absolute top-[1266.75px] left-[38px] h-[169.949px] w-[65px] rotate-180 xl:top-[842px]">
        <img src={asset("objects-a.svg")} alt="" className="absolute top-0 left-0 h-[152.672px] w-[20.975px]" />
        <img src={asset("objects-b.svg")} alt="" className="absolute right-0 bottom-0 h-[152.672px] w-[20.975px]" />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div className="relative isolate overflow-x-clip">
      <Decorations />
      <Header />
      <main>
        <Hero />
        <Partners />
        <Services />
        <Destinations />
        <TravelPoint />
        <KeyFeatures />
        <Testimonials />
        <Newsletter />
      </main>
      <Footer />
    </div>
  );
}
