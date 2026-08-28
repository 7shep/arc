"use client";

import type { CourseGraph as CourseGraphData } from "@arc/shared";
import { Background, Controls, Edge, MarkerType, Node, ReactFlow } from "@xyflow/react";
import { useMemo } from "react";

const colors = { CONCEPT: "#087a55", LECTURE: "#37614f", ASSIGNMENT: "#8a5a20", DOCUMENT: "#52616b", EXAMPLE: "#52616b", FORMULA: "#52616b", QUESTION: "#52616b" };

export function CourseGraph({ graph }: { graph: CourseGraphData }) {
  const flow = useMemo(() => {
    const columns = Math.max(3, Math.ceil(Math.sqrt(graph.nodes.length)));
    const nodes: Node[] = graph.nodes.map((node, index) => ({
      id: node.id,
      position: { x: (index % columns) * 230 + (index % 2) * 35, y: Math.floor(index / columns) * 155 + (index % 3) * 18 },
      data: { label: <div><span className="mb-1 block font-mono text-[10px] tracking-[0.08em] opacity-65">{node.type}</span><strong className="text-sm font-medium">{node.label}</strong></div> },
      style: { width: 180, borderRadius: 0, border: `1px solid ${colors[node.type]}`, borderLeft: `4px solid ${colors[node.type]}`, background: "#fff", color: "#171a18", padding: "12px 14px", boxShadow: "none" },
    }));
    const edges: Edge[] = graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.sourceNodeId,
      target: edge.targetNodeId,
      label: edge.type.replaceAll("_", " ").toLowerCase(),
      type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed, color: "#829087", width: 15, height: 15 },
      style: { stroke: "#829087", strokeWidth: 1.25 },
      labelStyle: { fill: "#68716b", fontSize: 10, fontFamily: "monospace" },
      labelBgStyle: { fill: "#f7f9f7", fillOpacity: 0.95 },
    }));
    return { nodes, edges };
  }, [graph]);

  return <div className="graph-grid h-[560px] border border-[var(--line)] bg-[#f7f9f7]" aria-label={`Knowledge graph with ${graph.nodes.length} nodes and ${graph.edges.length} relationships`}><ReactFlow nodes={flow.nodes} edges={flow.edges} fitView fitViewOptions={{ padding: 0.18 }} minZoom={0.45} maxZoom={1.5} nodesDraggable nodesConnectable={false} elementsSelectable><Background color="transparent" /><Controls showInteractive={false} position="bottom-right" /></ReactFlow></div>;
}

