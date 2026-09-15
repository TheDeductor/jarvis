// Avatars.tsx — occupant avatars for the 3D scene.
//
// The CC0 people models are rigged and skinned (10-20 clips each), so they cannot be
// drawn with InstancedMesh: every avatar needs its own skeleton. Each avatar is a
// SkeletonUtils clone driven by a shared clip through its own AnimationMixer, and all
// mixers are advanced from ONE useFrame subscription instead of one per avatar.
//
// Avatar size is derived from the rig itself: the ankle-to-head bone span is measured
// once per model and scaled to AVATAR_BONE_SPAN_M, which sidesteps the fact that the
// four rigs are published at wildly different unit scales (measured spans: 0.90, 0.91,
// 4.23 and 5.16 model units).

import { memo, useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import { clone as cloneSkinned } from 'three/examples/jsm/utils/SkeletonUtils.js';
import { AVATAR_CLIP, AVATAR_URL, type AvatarKind, type Seat } from './models';

// Ankle-to-head-joint span of a ~1.75 m adult; the skull adds the rest.
const AVATAR_BONE_SPAN_M = 1.5;

export interface AvatarSpec extends Seat {
  kind: AvatarKind;
}

type MixerList = { current: THREE.AnimationMixer[] };

function boneSpan(object: THREE.Object3D): number {
  object.updateMatrixWorld(true);
  const point = new THREE.Vector3();
  let min = Infinity;
  let max = -Infinity;
  object.traverse((child) => {
    if (!(child as THREE.Bone).isBone) return;
    child.getWorldPosition(point);
    if (point.y < min) min = point.y;
    if (point.y > max) max = point.y;
  });
  return max > min ? max - min : 0;
}

const Avatar = memo(function Avatar({
  source,
  clip,
  scale,
  spec,
  mixers,
  phase,
}: {
  source: THREE.Object3D;
  clip: THREE.AnimationClip;
  scale: number;
  spec: AvatarSpec;
  mixers: MixerList;
  phase: number;
}) {
  const { object, mixer } = useMemo(() => {
    const clone = cloneSkinned(source);
    // Bind-pose bounds are tiny on skinned rigs, so three would cull avatars that are
    // actually on screen. The scene is small; culling them buys nothing.
    clone.traverse((child) => {
      if ((child as THREE.SkinnedMesh).isSkinnedMesh) child.frustumCulled = false;
    });
    const instanceMixer = new THREE.AnimationMixer(clone);
    const action = instanceMixer.clipAction(clip);
    action.play();
    // Desynchronise the loop so a room full of avatars does not move in lockstep.
    instanceMixer.setTime(phase * clip.duration);
    return { object: clone, mixer: instanceMixer };
  }, [source, clip, phase]);

  useEffect(() => {
    mixers.current.push(mixer);
    return () => {
      mixers.current = mixers.current.filter((candidate) => candidate !== mixer);
      mixer.stopAllAction();
    };
  }, [mixer, mixers]);

  return (
    <group position={[spec.x, 0, spec.z]} rotation={[0, spec.ry, 0]} scale={scale}>
      <primitive object={object} />
    </group>
  );
});

function AvatarGroup({
  kind,
  specs,
  mixers,
}: {
  kind: AvatarKind;
  specs: AvatarSpec[];
  mixers: MixerList;
}) {
  const { scene, animations } = useGLTF(AVATAR_URL[kind]);

  const scale = useMemo(() => {
    const span = boneSpan(scene);
    return span > 0 ? AVATAR_BONE_SPAN_M / span : 1;
  }, [scene]);

  const clip = useMemo(() => {
    const wanted = AVATAR_CLIP[kind];
    return (
      animations.find((candidate) => candidate.name === wanted) ??
      animations.find((candidate) => candidate.name.endsWith(wanted)) ??
      animations[0]
    );
  }, [animations, kind]);

  return (
    <>
      {specs.map((spec, index) => (
        <Avatar
          key={`${spec.x}:${spec.z}`}
          source={scene}
          clip={clip}
          scale={scale}
          spec={spec}
          mixers={mixers}
          phase={(index * 0.37) % 1}
        />
      ))}
    </>
  );
}

export default function Avatars({ specs }: { specs: AvatarSpec[] }) {
  const mixers = useRef<THREE.AnimationMixer[]>([]);

  useFrame((_, delta) => {
    for (const mixer of mixers.current) mixer.update(delta);
  });

  const byKind = useMemo(() => {
    const groups = new Map<AvatarKind, AvatarSpec[]>();
    for (const spec of specs) {
      const list = groups.get(spec.kind);
      if (list) list.push(spec);
      else groups.set(spec.kind, [spec]);
    }
    return [...groups.entries()];
  }, [specs]);

  return (
    <>
      {byKind.map(([kind, list]) => (
        <AvatarGroup key={kind} kind={kind} specs={list} mixers={mixers} />
      ))}
    </>
  );
}
