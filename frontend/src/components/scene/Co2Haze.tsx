// Co2Haze.tsx — semi-transparent atmospheric haze driven by live co2_ppm.
//
// The haze volume fills the room interior. Opacity smoothly lerps toward the
// target value derived from co2_ppm so that transitions (both rising and
// falling) are visible in real time as the backend state changes.
//
// Deliberately NOT smoke/fire colours — the haze is a warm straw-yellow at low
// CO2 and shifts toward a deeper amber at high CO2, suggesting stale air
// without alarming the viewer. At or below 800 ppm the volume is invisible.
//
// All animation runs inside useFrame. The co2_ppm prop is stored in a ref so
// useFrame always sees the latest value without re-rendering the component.

import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

// Room interior clearance for the haze box (slightly inset from the 6×5 m shell)
const HAZE_W = 5.7;
const HAZE_D = 4.7;
const HAZE_H = 2.4;   // full height of the air column
const HAZE_Y = 1.2;   // centre-height of the box (half HAZE_H above floor)

/** Map co2_ppm → target opacity: 0 at ≤800, up to 0.16 at ≥1500 ppm */
function ppmToOpacity(ppm: number): number {
  if (ppm <= 800) return 0;
  if (ppm >= 1500) return 0.16;
  return ((ppm - 800) / 700) * 0.16;
}

// Two anchor colours for lerping the haze tint
const COLOR_FRESH = new THREE.Color('#a8d060');  // greenish-yellow: fresh/low CO2
const COLOR_STALE = new THREE.Color('#c09020');  // warm amber: stale/high CO2

/** Map co2_ppm → haze colour: greener at low, amber at high */
function ppmToColor(ppm: number): THREE.Color {
  const t = Math.max(0, Math.min(1, (ppm - 800) / 700));
  return new THREE.Color().lerpColors(COLOR_FRESH, COLOR_STALE, t);
}

export default function Co2Haze({ co2_ppm }: { co2_ppm: number }) {
  const meshRef = useRef<THREE.Mesh>(null);
  // Store prop in ref so useFrame sees latest without triggering a re-render
  const ppmRef = useRef(co2_ppm);
  ppmRef.current = co2_ppm;
  // Stagger the breathing phase per room (initial random offset baked at mount)
  const timeRef = useRef(Math.random() * Math.PI * 2);

  useFrame((_, delta) => {
    timeRef.current += delta * 0.4;
    if (!meshRef.current) return;
    const mat = meshRef.current.material as THREE.MeshBasicMaterial;

    const targetOpacity = ppmToOpacity(ppmRef.current);
    // Subtle ±8 % breathing oscillation so the haze feels atmospheric
    const breathe = 1 + Math.sin(timeRef.current) * 0.08;
    // Lerp toward target — slow enough to be readable, fast enough to be live
    mat.opacity = THREE.MathUtils.lerp(mat.opacity, targetOpacity * breathe, delta * 1.5);
    mat.color.copy(ppmToColor(ppmRef.current));
  });

  return (
    <mesh ref={meshRef} position={[0, HAZE_Y, 0]}>
      <boxGeometry args={[HAZE_W, HAZE_H, HAZE_D]} />
      <meshBasicMaterial
        color={COLOR_FRESH}
        transparent
        opacity={0}
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}
