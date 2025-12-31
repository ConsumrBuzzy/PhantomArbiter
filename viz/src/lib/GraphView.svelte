<script lang="ts">
    import { onMount, onDestroy } from "svelte";
    import Graph from "graphology";
    import Sigma from "sigma";
    import forceAtlas2 from "graphology-layout-forceatlas2";
    import type { GraphPayload, GraphNode, GraphLink } from "./types";

    export let initialData: GraphPayload | null = null;

    let container: HTMLDivElement;
    let graph: Graph = new Graph();
    let renderer: Sigma;

    onMount(() => {
        // Initialize Sigma
        renderer = new Sigma(graph, container, {
            renderEdgeLabels: true,
            defaultNodeColor: "#808080",
            defaultEdgeColor: "#444",
            labelColor: { color: "#fff" },
        });

        if (initialData) {
            applyPayload(initialData);
        }
    });

    onDestroy(() => {
        if (renderer) renderer.kill();
    });

    /**
     * Public method to apply updates from the bridge
     */
    export function applyPayload(payload: GraphPayload) {
        if (payload.type === "snapshot") {
            graph.clear();
            payload.nodes.forEach(addNode);
            payload.links.forEach(addLink);
        } else if (payload.type === "diff") {
            // 1. Remove
            payload.removed_node_ids.forEach((id) => {
                if (graph.hasNode(id)) graph.dropNode(id);
            });
            payload.removed_links.forEach((l) => {
                if (graph.hasEdge(l.source, l.target)) {
                    graph.dropEdge(l.source, l.target);
                }
            });

            // 2. Upsert (Add or Update)
            payload.nodes.forEach(addNode);
            payload.links.forEach(addLink);
        }

        return {
            nodes: graph.order,
            links: graph.size,
        };
    }

    function addNode(n: GraphNode) {
        if (graph.hasNode(n.id)) {
            graph.mergeNodeAttributes(n.id, {
                label: n.label,
                color: n.color,
                size: n.size,
                ...n.meta,
            });
        } else {
            graph.addNode(n.id, {
                x: Math.random(),
                y: Math.random(),
                label: n.label,
                color: n.color,
                size: n.size,
                ...n.meta,
            });

            // Re-sync layout if needed
            if (!forceAtlas2.isRunning(graph)) {
                forceAtlas2.assign(graph, {
                    iterations: 50,
                    settings: { gravity: 1 },
                });
            }
        }
    }

    function addLink(l: GraphLink) {
        if (graph.hasEdge(l.source, l.target)) {
            graph.mergeEdgeAttributes(l.source, l.target, {
                weight: l.weight,
                color: l.color,
                label: l.label,
            });
        } else {
            // Forceatlas2 and other layouts benefit from 'weight' being strictly positive
            graph.addEdge(l.source, l.target, {
                weight: Math.max(l.weight, 0.1),
                color: l.color,
                label: l.label,
            });
        }
    }
</script>

<div bind:this={container} class="graph-container"></div>

<style>
    .graph-container {
        width: 100%;
        height: 100vh;
        background: #0b0e11;
    }
</style>
