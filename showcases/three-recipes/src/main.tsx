import "@fontsource/fraunces/500.css";
import "@fontsource/fraunces/600.css";
import "@fontsource/source-sans-3/400.css";
import "@fontsource/source-sans-3/600.css";
import "./styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { FloatingShapes, floatingCamera } from "./three/FloatingShapes";
import { GradientFlow } from "./three/GradientFlow";
import { Scene3D } from "./three/Scene3D";
import { WaveField } from "./three/WaveField";

const fallback = <div className="h-full w-full bg-gradient-to-br from-primary to-accent" />;

function Hero({ title, text, scene, dark = false }: { title: string; text: string; scene: React.ReactNode; dark?: boolean }) {
  return (
    <section className={`${dark ? "dark" : ""} relative isolate overflow-hidden bg-background text-foreground`}>
      <div className="absolute inset-0 -z-10">{scene}</div>
      <div className="mx-auto flex min-h-[560px] max-w-6xl flex-col justify-end gap-4 px-6 py-16">
        <h2 className="max-w-[16ch] font-display text-[clamp(2.2rem,6vw,4.2rem)] leading-[1.05] font-semibold text-balance">{title}</h2>
        <p className="max-w-[46ch] text-lg text-foreground">{text}</p>
      </div>
    </section>
  );
}

function App() {
  return (
    <main>
      <Hero dark title="Know exactly what to review today" text="WaveField: a wireframe grid rolling like a topographic map. Calm and technical." scene={<Scene3D className="h-full" fallback={fallback} camera={{ position: [0, 0, 5], fov: 45 }}><WaveField /></Scene3D>} />
      <Hero title="Learn by building, one lesson at a time" text="GradientFlow: the theme's ink, saffron and paper, flowing slowly behind the headline." scene={<Scene3D className="h-full opacity-90" fallback={fallback} camera={{ position: [0, 0, 1] }}><GradientFlow /></Scene3D>} />
      <Hero title="Your topics, growing week by week" text="FloatingShapes: soft shapes that lean towards your pointer." scene={<Scene3D className="h-full" fallback={fallback} camera={floatingCamera}><FloatingShapes /></Scene3D>} />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
