
import { SceneManager } from './SceneManager.js';
import { StarSystemManager } from './StarSystemManager.js';
import { FleetManager } from './FleetManager.js';
import { EffectManager } from './EffectManager.js';
import { MiniMapManager } from './MiniMapManager.js';
import { SettingsManager } from './SettingsManager.js';

/**
 * GalaxyGame
 * The Main Entry Point for the Phantom Galaxy Strategy Sim.
 * Orchestrates the managers and routes data streams.
 */
export class GalaxyGame {
    constructor(containerId, apiUrl, wsUrl) {
        this.apiUrl = apiUrl;
        this.wsUrl = wsUrl;

        console.log("🌌 [GalaxyGame] Initializing Engine...");

        // 1. Initialize Managers
        this.scene = new SceneManager(containerId);
        this.effects = new EffectManager(this.scene);
        this.stars = new StarSystemManager(this.scene);
        this.fleet = new FleetManager(this.scene, this.stars);
        this.minimap = new MiniMapManager(this.scene, 'minimap-container');
        this.settings = new SettingsManager(this);

        // UI Refs
        this.fpsEl = document.getElementById('fps-counter');
        this.shipEl = document.getElementById('ship-counter');
        this.frameCount = 0;
        this.lastTime = performance.now();

        // 2. Start Loop
        this.clock = new THREE.Clock();
        this.animate();

        // 3. Connect Data
        this.fetchInitialState();
        this.connectWebSocket();
    }

    async fetchInitialState() {
        try {
            const response = await fetch(this.apiUrl);
            const objects = await response.json();
            console.log(`🌌[GalaxyGame] Loaded ${objects.length} systems.`);
            this.stars.updatePlanets(objects);
        } catch (e) {
            console.error("Failed to fetch state:", e);
        }
    }

    connectWebSocket() {
        console.log(`🔌[GalaxyGame] Connecting to ${this.wsUrl}...`);
        this.ws = new WebSocket(this.wsUrl);

        this.ws.onopen = () => console.log("🔗 [GalaxyGame] Connected.");

        this.ws.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                this.routeEvent(payload);
            } catch (e) {
                console.error("Parse Error:", e);
            }
        };

        this.ws.onclose = () => {
            console.warn("🔌 [GalaxyGame] Disconnected. Retrying...");
            setTimeout(() => this.connectWebSocket(), 3000);
        };
    }

    routeEvent(payload) {
        this.lastMsgTime = performance.now();
        switch (payload.type) {
            case 'STATE_SNAPSHOT':
            case 'BATCH_UPDATE':
                if (payload.data) this.stars.updatePlanets(payload.data);
                break;

            case 'ARCHETYPE_UPDATE':
                this.stars.updateArchetype(payload);
                break;

            case 'PRICE_FRAME':
                // High-speed update from FlashCache Bridge
                // payload.updates = { mint: {p, s}, ... }
                if (payload.updates) {
                    Object.entries(payload.updates).forEach(([mint, data]) => {
                        // Mock RSI-like movement based on price change direction for now
                        // Just random fluctuation to satisfy "moving/adjusting" visual request
                        // until backend sends real RSI stream
                        const mockRsi = 50 + (Math.random() - 0.5) * 20;
                        this.stars.updateNodeData(mint, { p: data.p, rsi: mockRsi });
                    });
                }
                break;

            case 'TRADE_CONVOY':
                // Batch of kinetic events
                if (payload.events && Array.isArray(payload.events)) {
                    payload.events.forEach(trade => this.fleet.spawnShip(trade));
                }
                break;

            case 'TRADE_EVENT':
                // Legacy single-event support
                this.fleet.spawnShip(payload.data);
                break;

            case 'PING':
                this.ws.send(JSON.stringify({ type: "PONG" }));
                break;
        }
    }

    animate() {
        requestAnimationFrame(() => this.animate());

        const delta = this.clock.getDelta();

        // Update Logic
        this.effects.update(delta);
        this.stars.update(delta);
        this.fleet.update(delta);
        this.minimap.update();

        // UI Updates (Intermittent)
        this.frameCount++;
        if (this.frameCount % 30 === 0) {
            if (this.shipEl) this.shipEl.innerText = this.fleet.mesh.count;

            // Simple FPS
            const now = performance.now();
            const fps = Math.round(1000 / (now - this.lastTime));
            if (this.fpsEl) this.fpsEl.innerText = fps;
            this.lastTime = now;

            // Network Health (Mock based on last message time)
            // ideally we track this.lastMsgTime in onmessage
            const timeSinceMsg = now - (this.lastMsgTime || now);
            const netStatus = document.querySelector("#status-bar .status-value:last-child");
            if (netStatus) {
                if (timeSinceMsg < 500) {
                    netStatus.innerText = "STABLE";
                    netStatus.style.color = "#0f0";
                    netStatus.style.textShadow = "0 0 5px #0f0";
                } else if (timeSinceMsg < 2000) {
                    netStatus.innerText = "LAGGING";
                    netStatus.style.color = "#ffaa00";
                    netStatus.style.textShadow = "0 0 5px #ffaa00";
                } else {
                    netStatus.innerText = "OFFLINE";
                    netStatus.style.color = "#ff0000";
                    netStatus.style.textShadow = "0 0 5px #ff0000";
                }
            }
        }

        // Render Main Scene
        this.scene.render();
    }
}

