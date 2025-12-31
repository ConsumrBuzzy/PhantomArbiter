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

    // Process a high-speed flash event
    processFlash(flash) {
        if (!this.graph.hasNode(flash.node)) {
            // V32: Organic Sprouting (Auto-Discovery)
            // If the node doesn't exist, Create It!
            console.log(`🌱 Sprouting Node: ${flash.label || flash.node}`);

            this.graph.addNode(flash.node, {
                label: flash.label || flash.node.slice(0, 4),
                x: Math.random() * 100,
                y: Math.random() * 100,
                size: 5,
                color: '#00ffff',
                energy: 0
            });
        }

        if (this.graph.hasNode(flash.node)) {
            // Instant energy injection
            this.graph.setNodeAttribute(flash.node, 'energy', flash.energy || 1.0);
            this.graph.setNodeAttribute(flash.node, 'color', flash.color || '#39ff14'); // Explicit flash color
            this.graph.setNodeAttribute(flash.node, 'size', 20.0); // Big spike
        }
    }

    // Decay energy over time (called from RAF)
    decayEnergy() {
        this.graph.forEachNode((node, attributes) => {
            if (attributes.energy > 0.1) {
                const newEnergy = attributes.energy * 0.95; // 5% decay per frame
                this.graph.setNodeAttribute(node, 'energy', newEnergy);
                this.graph.setNodeAttribute(node, 'size', Math.max(3, newEnergy * 15));
                if (newEnergy < 0.3) {
                    this.graph.setNodeAttribute(node, 'color', '#00ffff');
                }
            }
        });
    }

    cleanup() {
        if (this.layout) this.layout.kill();
        if (this.renderer) this.renderer.kill();
    }
}
