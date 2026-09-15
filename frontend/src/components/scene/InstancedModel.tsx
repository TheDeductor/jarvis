// InstancedModel.tsx — draws one .glb many times with real InstancedMesh instancing.
//
// A Kenney/Furniture-Kit model can hold several primitives (desk = 2, chairDesk = 2),
// and only same-geometry primitives can share an InstancedMesh. So the loaded model is
// split into "parts" (one per primitive) and each part gets a single InstancedMesh
// covering every placement of that model in the whole building — e.g. all 9 desks are
// 2 draw calls, not 18.
//
// Placement transforms are composed as: placement * part matrix, so a placement reads
// as "put this model here, standing on the floor, centred on its footprint".

import { useLayoutEffect, useMemo, useRef } from 'react';
import { useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import { FURNITURE_SCALE, type Placement } from './models';

interface Part {
  geometry: THREE.BufferGeometry;
  material: THREE.Material;
  local: THREE.Matrix4;
}

function scaleOf(scale: Placement['scale']): [number, number, number] {
  if (scale === undefined) return [FURNITURE_SCALE, FURNITURE_SCALE, FURNITURE_SCALE];
  if (typeof scale === 'number') {
    const uniform = scale * FURNITURE_SCALE;
    return [uniform, uniform, uniform];
  }
  return [
    scale[0] * FURNITURE_SCALE,
    scale[1] * FURNITURE_SCALE,
    scale[2] * FURNITURE_SCALE,
  ];
}

export default function InstancedModel({
  url,
  placements,
}: {
  url: string;
  placements: Placement[];
}) {
  const { scene } = useGLTF(url);
  const partRefs = useRef<(THREE.InstancedMesh | null)[]>([]);

  const parts = useMemo<Part[]>(() => {
    const found: Part[] = [];
    scene.updateMatrixWorld(true);
    scene.traverse((object) => {
      const mesh = object as THREE.Mesh;
      if (!mesh.isMesh) return;
      found.push({
        geometry: mesh.geometry,
        material: Array.isArray(mesh.material) ? mesh.material[0] : mesh.material,
        local: mesh.matrixWorld.clone(),
      });
    });

    const bounds = new THREE.Box3();
    for (const part of found) {
      const probe = part.geometry.clone().applyMatrix4(part.local);
      probe.computeBoundingBox();
      if (probe.boundingBox) bounds.union(probe.boundingBox);
      probe.dispose();
    }

    // Source models are authored with the origin on a footprint corner; move the
    // origin to the footprint centre at floor level so placements stay readable.
    const centre = bounds.getCenter(new THREE.Vector3());
    const recentre = new THREE.Matrix4().makeTranslation(-centre.x, -bounds.min.y, -centre.z);
    for (const part of found) part.local.premultiply(recentre);

    return found;
  }, [scene]);

  useLayoutEffect(() => {
    const matrix = new THREE.Matrix4();
    const quaternion = new THREE.Quaternion();
    const euler = new THREE.Euler();
    const position = new THREE.Vector3();
    const scaling = new THREE.Vector3();

    parts.forEach((part, index) => {
      const instanced = partRefs.current[index];
      if (!instanced) return;
      placements.forEach((placement, i) => {
        const [px, py, pz] = scaleOf(placement.scale);
        scaling.set(px, py, pz);
        euler.set(0, placement.ry ?? 0, 0);
        quaternion.setFromEuler(euler);
        position.set(placement.x, placement.y ?? 0, placement.z);
        matrix.compose(position, quaternion, scaling).multiply(part.local);
        instanced.setMatrixAt(i, matrix);
      });
      instanced.instanceMatrix.needsUpdate = true;
    });
  }, [parts, placements]);

  return (
    <>
      {parts.map((part, index) => (
        <instancedMesh
          key={index}
          ref={(node) => {
            partRefs.current[index] = node;
          }}
          args={[part.geometry, part.material, placements.length]}
          castShadow
          receiveShadow
          frustumCulled={false}
        />
      ))}
    </>
  );
}
