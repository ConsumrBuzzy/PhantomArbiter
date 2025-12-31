<script lang="ts">
    import { onMount } from "svelte";
    import GraphView from "./lib/GraphView.svelte";
    import { BridgeClient } from "./lib/BridgeClient";
    import type { GraphPayload } from "./lib/types";

    let graphView: GraphView;
    let bridge: BridgeClient;
    
    let status: "connected" | "disconnected" | "connecting" = "connecting";
    let stats = { nodes: 0, links: 0, sequence: 0 };

    onMount(() => {
        bridge = new BridgeClient("ws://localhost:8765", (payload: GraphPayload) => {
            status = "connected";
            stats.sequence = payload.sequence;
            
            // Apply to Graph
            if (graphView) {
                graphView.applyPayload(payload);
            }

            // Update local stats (Simplified for UI)
            if (payload.type === "snapshot") {
                stats.nodes = payload.nodes.length;
                stats.links = payload.links.length;
            } else {
                // Approximate for Diffs
                stats.nodes += (payload.nodes.length - payload.removed_node_ids.length);
                stats.links += (payload.links.length - payload.removed_links.length);
            }
        });

        bridge.connect();

        return () => {
            bridge.close();
        };
    });
</script>

<main>
    <div class="hud">
        <div class="header">
            <h1>PRISM HUD <span class="version">v0.1</span></h1>
            <div class="status {status}">
                <div class="dot"></div>
                {status.toUpperCase()}
            </div>
        </div>
        
        <div class="stats">
            <div class="stat">
                <span class="label">NODES</span>
                <span class="value">{stats.nodes}</span>
            </div>
            <div class="stat">
                <span class="label">LINKS</span>
                <span class="value">{stats.links}</span>
            </div>
            <div class="stat">
                <span class="label">SEQ</span>
                <span class="value">#{stats.sequence}</span>
            </div>
        </div>
    </div>

    <GraphView bind:this={graphView} />
</main>

<style>
    :global(body) {
        margin: 0;
        padding: 0;
        overflow: hidden;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }

    main {
        position: relative;
        width: 100vw;
        height: 100vh;
        background: #000;
    }

    .hud {
        position: absolute;
        top: 20px;
        left: 20px;
        z-index: 100;
        pointer-events: none;
        color: white;
        background: rgba(11, 14, 17, 0.8);
        backdrop-filter: blur(10px);
        padding: 20px;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    }

    .header {
        display: flex;
        align-items: center;
        gap: 20px;
        margin-bottom: 15px;
    }

    h1 {
        margin: 0;
        font-size: 1.2rem;
        letter-spacing: 2px;
        font-weight: 800;
        color: #fff;
    }

    .version {
        font-size: 0.7rem;
        opacity: 0.5;
        vertical-align: middle;
    }

    .status {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.7rem;
        font-weight: bold;
        padding: 4px 8px;
        border-radius: 4px;
        background: rgba(0,0,0,0.3);
    }

    .dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #555;
    }

    .status.connected .dot { background: #00ff88; box-shadow: 0 0 10px #00ff88; }
    .status.connecting .dot { background: #ffaa00; }
    .status.disconnected .dot { background: #ff4444; }

    .stats {
        display: flex;
        gap: 25px;
    }

    .stat {
        display: flex;
        flex-direction: column;
    }

    .label {
        font-size: 0.6rem;
        font-weight: bold;
        opacity: 0.5;
        margin-bottom: 2px;
    }

    .value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.1rem;
        color: #00ff88;
    }
</style>
