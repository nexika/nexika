/**
 * lawha recipe: a slow flowing gradient made of three brand colours, as a full-bleed backdrop.
 * Colours from the design tokens (`--primary`, `--accent`, `--background`).
 * `veil` (0..1, default 0.55) blends the colours towards the page background so text on top stays
 * readable; lower it only when no text sits on the gradient (lawha check measures the real contrast).
 * Use inside <Scene3D camera={{ position: [0, 0, 1] }}>; still under "reduce motion".
 */
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Color, type ShaderMaterial } from "three";
import { token } from "./Scene3D";

const vertex = /* glsl */ `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

const fragment = /* glsl */ `
  uniform float uTime;
  uniform vec3 uA;
  uniform vec3 uB;
  uniform vec3 uC;
  uniform float uVeil;
  varying vec2 vUv;
  void main() {
    vec2 p = vUv * 2.0 - 1.0;
    float a = sin(p.x * 2.1 + uTime * 0.35) + sin(p.y * 3.0 - uTime * 0.25) + sin((p.x + p.y) * 1.7 + uTime * 0.2);
    float b = cos(p.x * 1.3 - uTime * 0.3) * cos(p.y * 2.2 + uTime * 0.15);
    vec3 col = mix(uA, uB, smoothstep(-1.5, 1.5, a));
    col = mix(col, uC, smoothstep(0.2, 1.0, b) * 0.55);
    col = mix(col, uC, uVeil);
    gl_FragColor = vec4(col, 1.0);
  }
`;

export function GradientFlow({ speed = 1, veil = 0.55 }: { speed?: number; veil?: number }) {
  const material = useRef<ShaderMaterial>(null);
  const uniforms = useMemo(() => ({
    uTime: { value: 2.0 },
    uA: { value: new Color(token("--primary", "#1f3a5f")) },
    uB: { value: new Color(token("--accent", "#e5a93b")) },
    uC: { value: new Color(token("--background", "#faf7f2")) },
    uVeil: { value: Math.min(1, Math.max(0, veil)) },
  }), [veil]);
  useFrame((_, delta) => {
    if (material.current) material.current.uniforms.uTime!.value += delta * speed;
  });
  return (
    <mesh frustumCulled={false}>
      <planeGeometry args={[2, 2]} />
      <shaderMaterial ref={material} vertexShader={vertex} fragmentShader={fragment} uniforms={uniforms} depthWrite={false} />
    </mesh>
  );
}
