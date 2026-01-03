
import { SceneManager } from './SceneManager.js';
import { StarSystemManager } from './StarSystemManager.js';
import { FleetManager } from './FleetManager.js';
import { EffectManager } from './EffectManager.js';

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
            console.log(`🌌 [GalaxyGame] Loaded ${objects.length} systems.`);
            this.stars.updatePlanets(objects);
        } catch (e) {
            console.error("Failed to fetch state:", e);
        }
    }

    connectWebSocket() {
        console.log(`🔌 [GalaxyGame] Connecting to ${this.wsUrl}...`);
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
                // Implementation: Could update planet labels or spawn micro-fleets
                // For now, let's just use it to update labels efficiently
                // this.stars.updatePrices(payload.updates);
                break;

            case 'TRADE_EVENT':
                // payload.data = { mint, is_buy, ... }
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

        // Render
        this.scene.render();
    }
}
