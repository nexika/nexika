import { useState } from "react";
import { Hero, Header } from "./sections/Hero";
import { Partners, Services, Destinations } from "./sections/Middle";
import { TravelPoint, Features, Testimonials } from "./sections/Lower";
import { Newsletter, Footer } from "./sections/Bottom";

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="relative min-h-screen bg-white font-circular-std text-grey-scale-black">
      <Header menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((o) => !o)} />
      <main>
        <Hero />
        <Partners />
        <Services />
        <Destinations />
        <TravelPoint />
        <Features />
        <Testimonials />
        <Newsletter />
      </main>
      <Footer />
    </div>
  );
}
