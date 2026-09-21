import { useEffect, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { MeshDistortMaterial } from "@react-three/drei";
import type { Mesh } from "three";

import { useTheme } from "../../lib/theme-provider";

/**
 * Reads `--primary` straight off the resolved CSS instead of a hardcoded hex
 * - the one hex value for the brand colour lives in tokens.css, and nothing
 * else, including the WebGL material, should carry its own copy that could
 * drift the next time the token changes. Re-reads on `resolvedTheme` flips
 * since light/dark resolve to different literal blues.
 */
function usePrimaryColor(): string {
  const { resolvedTheme } = useTheme();
  const [color, setColor] = useState("#1d4ed8");

  useEffect(() => {
    const value = getComputedStyle(document.documentElement).getPropertyValue("--primary").trim();
    if (value) setColor(value);
  }, [resolvedTheme]);

  return color;
}

/**
 * The hero's centerpiece: a metaball-style distorted sphere that leans
 * toward the pointer and drifts on its own between moves. Default export,
 * loaded via `React.lazy` from the caller (Hero, CallToAction) so the
 * three.js/@react-three/fiber chunk is only fetched once `useCanRenderWebGL()`
 * (lib/motion.ts) has already said yes - never bundled into the main chunk,
 * never fetched on a device that will only ever see `BlobFallback`.
 *
 * Disposal: every geometry/material below is JSX-declared and managed by
 * `@react-three/fiber`'s own reconciler, which disposes them automatically
 * on unmount by default (`dispose` is only ever `null` if a caller opts out,
 * which nothing here does) - so there is no manual `.dispose()` call to
 * write, and unmounting `<Canvas>` (leaving the page) releases the WebGL
 * context the same way.
 */
function DistortedBlob({ color }: { color: string }) {
  const meshRef = useRef<Mesh>(null);
  const pointer = useRef({ x: 0, y: 0 });
  const baseRotation = useRef(0);
  const lean = useRef({ x: 0, y: 0 });

  useEffect(() => {
    function onMove(e: PointerEvent) {
      pointer.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.current.y = (e.clientY / window.innerHeight) * 2 - 1;
    }
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  // Frame-rate independent throughout: every accumulator advances by
  // `delta`, not by a fixed per-frame step, so the drift/lean speed reads
  // the same at 30fps and 120fps.
  useFrame((_, delta) => {
    const mesh = meshRef.current;
    if (!mesh) return;

    baseRotation.current += delta * 0.15;

    const targetLeanY = pointer.current.x * 0.5;
    const targetLeanX = pointer.current.y * 0.35;
    const t = Math.min(delta * 3, 1);
    lean.current.x += (targetLeanX - lean.current.x) * t;
    lean.current.y += (targetLeanY - lean.current.y) * t;

    mesh.rotation.y = baseRotation.current + lean.current.y;
    mesh.rotation.x = lean.current.x;
  });

  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[1.4, 64, 64]} />
      {/* `metalness: 0` deliberately - a PBR material with any metalness
          renders near-black without a reflection environment map to sample,
          which is what made the very first pass of this invisible against
          the page background despite the canvas itself rendering correctly.
          `emissive` guarantees a visible base colour regardless of how the
          lights below land, with the two directional lights on top of it
          for the actual shading that makes it read as a lit 3D surface
          rather than a flat circle. */}
      <MeshDistortMaterial
        color={color}
        emissive={color}
        emissiveIntensity={0.5}
        distort={0.4}
        speed={1.8}
        roughness={0.35}
        metalness={0}
      />
    </mesh>
  );
}

export default function LiquidBlob() {
  const color = usePrimaryColor();

  return (
    <Canvas
      dpr={[1, 2]}
      camera={{ position: [0, 0, 4], fov: 40 }}
      // `preserveDrawingBuffer` costs a little perf and nothing visually for
      // a real viewer, but without it an automated screenshot tool can grab
      // the buffer between WebGL's own clear and the next submitted frame
      // and capture nothing - which is exactly what happened verifying this
      // component, even though the canvas was genuinely rendering.
      gl={{ antialias: true, alpha: true, preserveDrawingBuffer: true }}
      // Transparent clear colour - the page's own background/gradient washes
      // show through around the blob instead of a solid canvas rectangle.
      onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
    >
      <ambientLight intensity={1.1} />
      <directionalLight position={[2, 2, 3]} intensity={2.4} />
      <directionalLight position={[-2, -1, -2]} intensity={0.8} />
      <DistortedBlob color={color} />
    </Canvas>
  );
}
