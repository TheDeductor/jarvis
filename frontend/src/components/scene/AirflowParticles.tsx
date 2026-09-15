// AirflowParticles.tsx — lightweight upward airflow particle stream.
//
// A fixed pool of N_PARTICLES per room implemented as a single THREE.Points
// draw call. Particle y-positions are updated in-place inside useFrame; no
// THREE.BufferGeometry recreation, no React re-renders, no allocations per frame.
//
// Speed and opacity both scale with airflow_lps:
//   • baseline ~60 L/s  → slow drift, barely visible
//   • INCREASE_AIRFLOW ~145 L/s → clear upward movement
//   • manual high ~300 L/s → pronounced fast stream
//
// The prop is mirrored into a ref so useFrame always reads the latest value
// without the component re-rendering. Opacity also lerps smoothly so the viewer
// can watch it ramp up when the IAQ rule fires and fade when it recovers.
//
// Colour is a cool blue-white (#b8d8ff) — reads as "fresh supply air", not smoke.

import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

const N_PARTICLES = 40;
// Interior span for particle spawning (smaller than the 6×5 m room to avoid
// spawning inside walls)
const SPAWN_W = 5.0;
const SPAWN_D = 4.0;
const MAX_Y   = 2.7;  // ceiling height where particles wrap

const randX = () => (Math.random() - 0.5) * SPAWN_W;
const randZ = () => (Math.random() - 0.5) * SPAWN_D;

/** Map airflow_lps → vertical particle speed (visual m/s, not physical) */
function afToSpeed(lps: number): number {
  return 0.15 + (Math.min(lps, 300) / 300) * 1.2;
}

/** Map airflow_lps → overall opacity of the particle group */
function afToOpacity(lps: number): number {
  return Math.min(0.06 + (Math.min(lps, 300) / 300) * 0.34, 0.40);
}

export default function AirflowParticles({ airflow_lps }: { airflow_lps: number }) {
  const pointsRef = useRef<THREE.Points>(null);
  // Mirror prop into ref — useFrame reads this, never triggers re-render
  const afRef = useRef(airflow_lps);
  afRef.current = airflow_lps;

  // Allocate particle data once. speedMult gives each particle a slight
  // individual velocity variation so the stream looks organic.
  const { positions, speedMult } = useMemo(() => {
    const positions  = new Float32Array(N_PARTICLES * 3);
    const speedMult  = new Float32Array(N_PARTICLES);
    for (let i = 0; i < N_PARTICLES; i++) {
      positions[i * 3]     = randX();
      positions[i * 3 + 1] = Math.random() * MAX_Y;  // spread initial heights
      positions[i * 3 + 2] = randZ();
      speedMult[i]          = 0.55 + Math.random() * 0.9;
    }
    return { positions, speedMult };
  }, []);

  // Build the geometry once and keep the BufferAttribute reference for in-place updates
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    return geo;
  }, [positions]);

  useFrame((_, delta) => {
    const speed   = afToSpeed(afRef.current);
    const opacity = afToOpacity(afRef.current);

    // Advance each particle upward; wrap to the bottom when it exits the ceiling
    for (let i = 0; i < N_PARTICLES; i++) {
      positions[i * 3 + 1] += speed * speedMult[i] * delta;
      if (positions[i * 3 + 1] > MAX_Y) {
        positions[i * 3]     = randX();
        positions[i * 3 + 1] = -0.1 + Math.random() * 0.25;
        positions[i * 3 + 2] = randZ();
      }
    }

    if (pointsRef.current) {
      // In-place attribute update — no GC pressure
      (geometry.attributes.position as THREE.BufferAttribute).needsUpdate = true;
      // Lerp opacity for smooth transitions when airflow changes
      const mat = pointsRef.current.material as THREE.PointsMaterial;
      mat.opacity = THREE.MathUtils.lerp(mat.opacity, opacity, delta * 2.5);
    }
  });

  return (
    <points ref={pointsRef} geometry={geometry}>
      <pointsMaterial
        color="#b8d8ff"
        size={0.045}
        transparent
        opacity={afToOpacity(airflow_lps)}
        depthWrite={false}
        sizeAttenuation
      />
    </points>
  );
}
