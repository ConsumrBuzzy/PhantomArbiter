import Graph from 'graphology';
import Sigma from 'sigma';
import ForceSupervisor from 'graphology-layout-forceatlas2/worker';

export class SigmaManager {
    constructor(containerId) {
        this.containerId = containerId;
        this.graph = new Graph();
        this.renderer = null;
        this.layout = null;
    }

    initialize() {
        const container = document.getElementById(this.containerId);
        if (!container) {
            console.error(`Container #${this.containerId} not found`);
            return;
        }

        // Initial settings for "pretty" rendering
        this.renderer = new Sigma(this.graph, container, {
            renderEdgeLabels: false,
            allowInvalidContainer: true,
            labelDensity: 0.07,
            labelGridCellSize: 60,
            labelRenderedSizeThreshold: 15,
            zIndex: true
        });

        // Start ForceAtlas2 layout for organic movement
        this.layout = new ForceSupervisor(this.graph, {
            settings: {
                gravity: 1,
                scalingRatio: 4,
                barnesHutOptimize: true,
                barnesHutTheta: 0.6
            }
        });
        this.layout.start();
    }

    // Process a full snapshot (initial state)
    processSnapshot(snapshot) {
        // snapshot structure: { nodes: [], edges: [], ... }
        this.graph.clear(); // Clear existing for a fresh snapshot

        if (!snapshot.nodes) return;

        snapshot.nodes.forEach(node => {
            // "Glow" logic: Size based on energy or constant for now
            const size = node.energy ? Math.max(3, node.energy * 10) : 5;
            this.graph.addNode(node.id, {
                label: node.label || node.id,
                x: Math.random() * 100,
                y: Math.random() * 100,
                size: size,
                color: node.color || '#00ffff', // Default neon blue
                energy: node.energy || 0
            });
        });

        if (snapshot.edges) {
            snapshot.edges.forEach(edge => {
                if (!this.graph.hasEdge(edge.source, edge.target)) {
                    this.graph.addEdge(edge.source, edge.target, {
                        size: 2,
                        color: '#333333' // Dark grey for subtle connections
                    });
                }
            });
        }

        // Refresh layout if needed, or let ForceAtlas continue
        if (!this.layout.isRunning()) {
            this.layout.start();
        }
    }

    // Process a diff (real-time updates)
    processDiff(diff) {
        // diff structure: { updated_nodes: [], new_edges: [], ... }
        if (diff.updated_nodes) {
            diff.updated_nodes.forEach(uNode => {
                if (this.graph.hasNode(uNode.id)) {
                    // Update attributes, specifically "Glow" (size/color)
                    const energy = uNode.energy || 0;
                    this.graph.setNodeAttribute(uNode.id, 'energy', energy);

                    // Visual Pulse: High energy = Bright Green, Low = Blue
                    const color = energy > 0.8 ? '#39ff14' : '#00ffff';
                    this.graph.setNodeAttribute(uNode.id, 'color', color);

                    // Size pulse
                    this.graph.setNodeAttribute(uNode.id, 'size', Math.max(3, energy * 15));
                }
            });
        }

        // Add other diff logic (new nodes/edges) as needed
    }

    cleanup() {
        if (this.layout) this.layout.kill();
        if (this.renderer) this.renderer.kill();
    }
}
