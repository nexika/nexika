/**
 * lawha recipe: a few soft shapes floating slowly, leaning towards the pointer.
 * Friendly and light; colours from the design tokens. Use inside <Scene3D>; still under "reduce motion".
 * `side` keeps the shapes away from the text: "end" (default) is the side opposite the start of a line,
 * so it follows the page direction (right in English, left in Arabic).
 * Use with `camera={floatingCamera}`: a long lens from further away keeps spheres round; a wide lens
 * stretches shapes placed away from the centre.
 */
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { Group } from "three";
import { token } from "./Scene3D";

export const floatingCamera = { position: [0, 0, 11] as [number, number, number], fov: 24 };

export function FloatingShapes({ speed = 1, side = "end" }: { speed?: number; side?: "start" | "end" | "center" }) {
  const group = useRef<Group>(null);
  const rtl = typeof document !== "undefined" && document.documentElement.dir === "rtl";
  const offset = side === "center" ? 0 : (side === "end") !== rtl ? 2.3 : -2.3;
  const primary = token("--primary", "#1f3a5f");
  const accent = token("--accent", "#e5a93b");
  useFrame((state, delta) => {
    const g = group.current;
    if (!g) return;
    const t = state.clock.elapsedTime * speed;
    g.children.forEach((child, i) => {
      child.position.y = Math.sin(t * 0.8 + i * 1.7) * 0.25 + (i - 1) * 0.15;
      child.rotation.x += delta * 0.15 * speed;
      child.rotation.y += delta * 0.2 * speed;
    });
    g.rotation.y += (state.pointer.x * 0.25 - g.rotation.y) * 0.05;
    g.rotation.x += (-state.pointer.y * 0.15 - g.rotation.x) * 0.05;
  });
  return (
    <group ref={group} position={[offset, 0.35, 0]} scale={0.72}>
      <ambientLight intensity={0.7} />
      <directionalLight position={[3, 4, 5]} intensity={1.2} />
      <mesh position={[-1.6, 0, 0]}>
        <icosahedronGeometry args={[0.8, 0]} />
        <meshStandardMaterial color={primary} roughness={0.35} flatShading />
      </mesh>
      <mesh position={[0.2, 0.3, -0.5]}>
        <torusGeometry args={[0.6, 0.22, 24, 64]} />
        <meshStandardMaterial color={accent} roughness={0.3} />
      </mesh>
      <mesh position={[1.7, -0.2, 0.2]}>
        <sphereGeometry args={[0.55, 48, 48]} />
        <meshStandardMaterial color={primary} roughness={0.15} metalness={0.2} />
      </mesh>
    </group>
  );
}
