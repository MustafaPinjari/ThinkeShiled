"use client";

import React, { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import type { GraphData, GraphNode, GraphEdge, EdgeType } from "@/types/graph";

const EDGE_COLORS: Record<EdgeType, string> = {
  CO_BID: "#6366f1",
  SHARED_DIRECTOR: "#f59e0b",
  SHARED_ADDRESS: "#10b981",
};

const NODE_COLORS: Record<string, string> = {
  LOW: "#22c55e",
  MEDIUM: "#f59e0b",
  HIGH_RISK: "#ef4444",
};

interface GraphCanvasProps {
  data: GraphData;
  activeEdgeTypes: EdgeType[];
}

export default function GraphCanvas({ data, activeEdgeTypes }: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<unknown>(null);
  const router = useRouter();

  useEffect(() => {
    if (!containerRef.current || !data.nodes.length) return;

    const timer = setTimeout(async () => {
      if (!containerRef.current) return;

      try {
        // Import the full vis-network module
        const visNetwork = await import("vis-network/standalone");
        const { Network, DataSet } = visNetwork;

        const filteredEdges = data.edges.filter((e: GraphEdge) =>
          activeEdgeTypes.includes(e.type)
        );

        const nodesData = new DataSet(
          data.nodes.map((n: GraphNode) => ({
            id: n.id,
            label: n.label,
            title: `${n.label}\nRisk: ${n.risk_status}\nScore: ${n.fraud_score}`,
            color: {
              background: NODE_COLORS[n.risk_status] ?? "#94a3b8",
              border: "rgba(255,255,255,0.2)",
              highlight: { background: NODE_COLORS[n.risk_status] ?? "#94a3b8", border: "#fff" },
              hover: { background: NODE_COLORS[n.risk_status] ?? "#94a3b8", border: "#fff" },
            },
            font: { color: "#ffffff", size: 11, face: "Inter, sans-serif" },
            size: 20 + Math.min(n.fraud_score / 5, 16),
            borderWidth: n.risk_status === "HIGH_RISK" ? 2 : 1,
          }))
        );

        const edgesData = new DataSet(
          filteredEdges.map((e: GraphEdge) => ({
            id: e.id,
            from: e.source,
            to: e.target,
            color: { color: EDGE_COLORS[e.type] ?? "#6366f1", opacity: 0.7 },
            width: 2,
            title: e.type.replace(/_/g, " "),
            arrows: { to: { enabled: false } },
            smooth: { enabled: true, type: "dynamic", roundness: 0.3 },
          }))
        );

        const options = {
          physics: {
            enabled: true,
            forceAtlas2Based: {
              gravitationalConstant: -50,
              centralGravity: 0.01,
              springLength: 120,
              springConstant: 0.08,
            },
            solver: "forceAtlas2Based",
            stabilization: { iterations: 150 },
          },
          interaction: {
            hover: true,
            tooltipDelay: 200,
            zoomView: true,
            dragView: true,
            navigationButtons: false,
            keyboard: false,
          },
          layout: { improvedLayout: true },
          nodes: { shape: "dot" },
        };

        // Destroy previous instance
        if (networkRef.current) {
          (networkRef.current as { destroy: () => void }).destroy();
        }

        const network = new Network(
          containerRef.current!,
          { nodes: nodesData, edges: edgesData },
          options
        );
        networkRef.current = network;

        network.on("click", (params: { nodes: number[] }) => {
          if (params.nodes.length === 1) {
            router.push(`/companies/${params.nodes[0]}`);
          }
        });

        network.on("hoverNode", () => {
          if (containerRef.current) containerRef.current.style.cursor = "pointer";
        });
        network.on("blurNode", () => {
          if (containerRef.current) containerRef.current.style.cursor = "default";
        });

      } catch (err) {
        console.error("vis-network init error:", err);
      }
    }, 150);

    return () => {
      clearTimeout(timer);
      if (networkRef.current) {
        (networkRef.current as { destroy: () => void }).destroy();
        networkRef.current = null;
      }
    };
  }, [data, activeEdgeTypes, router]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", minHeight: "480px" }}
      aria-label="Collusion network graph"
    />
  );
}
