"use client";

import { Line, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

// The web as a quiet point sphere; a few sites in ink-blue, and an agent (a small blue mark) hopping
// between them along great-circle arcs. Monochrome, drag to turn, no zoom.

const R = 1.25;

function fibonacciSphere(n: number, radius: number): Float32Array {
  const pts = new Float32Array(n * 3);
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const t = golden * i;
    pts.set([Math.cos(t) * r * radius, y * radius, Math.sin(t) * r * radius], i * 3);
  }
  return pts;
}

function arc(a: THREE.Vector3, b: THREE.Vector3, segments = 48): THREE.Vector3[] {
  const out: THREE.Vector3[] = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const p = new THREE.Vector3().copy(a).lerp(b, t).normalize();
    const lift = 1 + Math.sin(Math.PI * t) * 0.12;
    out.push(p.multiplyScalar(R * lift));
  }
  return out;
}

function Scene() {
  const group = useRef<THREE.Group>(null);
  const agent = useRef<THREE.Mesh>(null);
  const dots = useMemo(() => fibonacciSphere(1400, R), []);
  const sites = useMemo(() => {
    // Neighbouring sites on the front of the sphere, so every hop is a short arc.
    const idx = [700, 740, 652, 610, 790, 676];
    return idx.map((i) => new THREE.Vector3(dots[i * 3], dots[i * 3 + 1], dots[i * 3 + 2]));
  }, [dots]);
  const routes = useMemo(() => sites.map((s, i) => arc(s, sites[(i + 1) % sites.length])), [sites]);

  useFrame((state, delta) => {
    if (group.current) group.current.rotation.y += delta * 0.06;
    if (agent.current) {
      const t = state.clock.elapsedTime * 0.22;
      const leg = Math.floor(t) % routes.length;
      const path = routes[leg];
      const k = t - Math.floor(t);
      const eased = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      const p = path[Math.min(path.length - 1, Math.round(eased * (path.length - 1)))];
      agent.current.position.copy(p);
    }
  });

  return (
    <group ref={group} rotation={[0.3, -0.4, 0.06]}>
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[dots, 3]} />
        </bufferGeometry>
        <pointsMaterial size={0.02} color="#2f3437" transparent opacity={0.55} sizeAttenuation />
      </points>
      {sites.map((s, i) => (
        <mesh key={i} position={s}>
          <sphereGeometry args={[0.026, 16, 16]} />
          <meshBasicMaterial color="#1f6c9f" />
        </mesh>
      ))}
      {routes.map((r, i) => <Line key={i} points={r} color="#1f6c9f" lineWidth={1} transparent opacity={0.28} />)}
      <mesh ref={agent}>
        <sphereGeometry args={[0.038, 16, 16]} />
        <meshBasicMaterial color="#111111" />
      </mesh>
    </group>
  );
}

export default function Globe() {
  return (
    <Canvas style={{ position: "absolute", inset: 0 }} camera={{ position: [0, 0, 5.4], fov: 40 }} dpr={[1, 2]} gl={{ antialias: true, alpha: true }} aria-label="A globe of websites with an AI agent travelling between them">
      <Scene />
      <OrbitControls enableZoom={false} enablePan={false} rotateSpeed={0.5} />
    </Canvas>
  );
}
