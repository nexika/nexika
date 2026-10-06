/**
 * lawha recipe: a wireframe wave field - a grid of lines rolling like a topographic map.
 * Calm, technical, good behind a dark hero. Colours from the design tokens.
 * Use inside <Scene3D>; it stands still under "reduce motion" (Scene3D renders one frame).
 */
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Color, type ShaderMaterial } from "three";
import { token } from "./Scene3D";

const vertex = /* glsl */ `
  uniform float uTime;
  uniform float uAmp;
  varying float vHeight;
  void main() {
    vec3 p = position;
    float w = sin(p.x * 0.9 + uTime * 0.6) * 0.5 + sin(p.y * 1.3 - uTime * 0.4) * 0.35 + sin((p.x + p.y) * 0.6 + uTime * 0.25) * 0.4;
    p.z += w * uAmp;
    vHeight = w;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;

const fragment = /* glsl */ `
  uniform vec3 uColor;
  uniform vec3 uGlow;
  varying float vHeight;
  void main() {
    float t = smoothstep(-1.0, 1.2, vHeight);
    gl_FragColor = vec4(mix(uColor, uGlow, t), 0.35 + 0.45 * t);
  }
`;

export function WaveField({ speed = 1, amplitude = 0.6, density = 64 }: { speed?: number; amplitude?: number; density?: number }) {
  const material = useRef<ShaderMaterial>(null);
  const uniforms = useMemo(() => ({
    uTime: { value: 1.7 },
    uAmp: { value: amplitude },
    uColor: { value: new Color(token("--muted-foreground", "#5d6370")) },
    uGlow: { value: new Color(token("--accent", "#e5a93b")) },
  }), [amplitude]);
  useFrame((_, delta) => {
    if (material.current) material.current.uniforms.uTime!.value += delta * speed;
  });
  return (
    <mesh rotation={[-1.05, 0, 0.2]} position={[0, -0.6, 0]}>
      <planeGeometry args={[14, 8, density, Math.round(density / 2)]} />
      <shaderMaterial ref={material} vertexShader={vertex} fragmentShader={fragment} uniforms={uniforms} wireframe transparent />
    </mesh>
  );
}
