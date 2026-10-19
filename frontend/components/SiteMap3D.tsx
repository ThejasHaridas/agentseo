"use client";

import { Html, Line, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { PageRow } from "@/lib/api";

// The crawled site in 3D: the homepage at the centre, every page placed on a shell by its URL depth and
// joined to its nearest crawled ancestor. Colour is how much of the page's text exists without JavaScript.

export interface MapNode { id: string; path: string; url: string; depth: number; ratio: number | null; status: number | null; title: string; pos: THREE.Vector3; parent: number | null }

export function ratioColor(r: number | null, status: number | null): string {
  if (status != null && status >= 400) return "#9f2f2d";
  if (r == null) return "#a5a49f";
  if (r >= 0.8) return "#346538";
  if (r >= 0.5) return "#956400";
  return "#9f2f2d";
}

export function buildNodes(pages: PageRow[]): MapNode[] {
  const parsed = pages.map((p) => {
    let path = p.url;
    try { const u = new URL(p.url); path = (u.pathname.replace(/\/index\.html?$/, "/") || "/") + u.search; } catch { /* keep url */ }
    const segs = path.split("/").filter(Boolean);
    return { p, path, segs };
  });
  parsed.sort((a, b) => a.segs.length - b.segs.length || a.path.localeCompare(b.path));
  const nodes: MapNode[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  const perDepth = new Map<number, number>();
  const countAt = new Map<number, number>();
  parsed.forEach(({ segs }) => countAt.set(segs.length, (countAt.get(segs.length) ?? 0) + 1));

  parsed.forEach(({ p, path, segs }) => {
    const depth = segs.length;
    const k = perDepth.get(depth) ?? 0;
    perDepth.set(depth, k + 1);
    const n = countAt.get(depth) ?? 1;
    let pos: THREE.Vector3;
    if (depth === 0 && k === 0) pos = new THREE.Vector3(0, 0, 0);
    else {
      const radius = 1.25 * Math.max(1, depth) + (depth === 0 ? 0.6 : 0);
      const y = n === 1 ? 0 : 1 - (k / (n - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const t = golden * k + depth;
      pos = new THREE.Vector3(Math.cos(t) * r, y * 0.75, Math.sin(t) * r).multiplyScalar(radius);
    }
    // Parent: the crawled page with the longest path that prefixes this one.
    let parent: number | null = null;
    let best = -1;
    nodes.forEach((m, i) => {
      const prefix = m.path === "/" ? "/" : m.path.replace(/\/$/, "") + "/";
      if (m.path !== path && path.startsWith(prefix) && prefix.length > best) { best = prefix.length; parent = i; }
    });
    if (parent === null && nodes.length && depth > 0) parent = 0;
    nodes.push({
      id: p.id, path, url: p.url, depth, ratio: (p.metrics.no_js_text_ratio as number | null | undefined) ?? null,
      status: p.status_code, title: (p.metrics.title as string) || "", pos, parent,
    });
  });
  return nodes;
}

function Node({ node, selected, onSelect }: { node: MapNode; selected: boolean; onSelect: (n: MapNode) => void }) {
  const [hover, setHover] = useState(false);
  const mesh = useRef<THREE.Mesh>(null);
  useFrame(() => {
    if (!mesh.current) return;
    const target = hover || selected ? 1.6 : 1;
    mesh.current.scale.lerp(new THREE.Vector3(target, target, target), 0.18);
  });
  const color = ratioColor(node.ratio, node.status);
  return (
    <group position={node.pos}>
      <mesh ref={mesh}
            onPointerOver={(e) => { e.stopPropagation(); setHover(true); document.body.style.cursor = "pointer"; }}
            onPointerOut={() => { setHover(false); document.body.style.cursor = ""; }}
            onClick={(e) => { e.stopPropagation(); onSelect(node); }}>
        <sphereGeometry args={[node.depth === 0 ? 0.13 : 0.075, 20, 20]} />
        <meshBasicMaterial color={color} />
      </mesh>
      {(hover || selected) && (
        <Html distanceFactor={7} position={[0, 0.22, 0]} center style={{ pointerEvents: "none" }}>
          <div className="tip" style={{ position: "static", transform: "none" }}>
            <span className="mono">{node.path}</span><br />
            {node.status != null && node.status >= 400 ? `HTTP ${node.status}` : node.ratio == null ? "Not rendered" : `${Math.round(node.ratio * 100)}% readable without JavaScript`}
          </div>
        </Html>
      )}
    </group>
  );
}

function Scene({ nodes, selected, onSelect }: { nodes: MapNode[]; selected: string | null; onSelect: (n: MapNode) => void }) {
  const group = useRef<THREE.Group>(null);
  useFrame((_, delta) => { if (group.current && !selected) group.current.rotation.y += delta * 0.08; });
  return (
    <group ref={group}>
      {nodes.map((n) => n.parent != null && (
        <Line key={`l-${n.id}`} points={[nodes[n.parent].pos, n.pos]} color="#2f3437" lineWidth={0.8} transparent opacity={0.16} />
      ))}
      {nodes.map((n) => <Node key={n.id} node={n} selected={selected === n.id} onSelect={onSelect} />)}
    </group>
  );
}

export default function SiteMap3D({ pages, selected, onSelect }: { pages: PageRow[]; selected: string | null; onSelect: (n: MapNode) => void }) {
  const nodes = useMemo(() => buildNodes(pages), [pages]);
  const reach = Math.max(4, ...nodes.map((n) => n.pos.length())) * 1.9;
  return (
    <Canvas camera={{ position: [0, reach * 0.45, reach], fov: 40 }} dpr={[1, 2]} gl={{ antialias: true, alpha: true }}
            onPointerMissed={() => onSelect({ id: "", } as MapNode)} aria-label="3D map of the crawled pages">
      <Scene nodes={nodes} selected={selected} onSelect={onSelect} />
      <OrbitControls enablePan={false} minDistance={3} maxDistance={reach * 1.6} rotateSpeed={0.6} />
    </Canvas>
  );
}
