import { BasePage } from '../core/base-page.js';

export class EnginePage extends BasePage {
    constructor(engineId) {
        super(engineId);
        this.engineId = engineId;
    }

    async render() {
        return `
            <div class="engine-page-container" style="padding: 20px; height: 100%; display: flex; flex-direction: column;">
                <header class="glass-panel" style="margin-bottom: 20px; display: flex; justify-content: space-between;">
                    <button class="back-btn" onclick="window.router.navigate('/dashboard')">← Back to Hub</button>
                    <h1>Engine Control: ${this.engineId.toUpperCase()}</h1>
                    <div class="engine-status">STOPPED</div>
                </header>

                <div class="engine-content-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; flex: 1;">
                    <!-- LEFT: High Frequency Data -->
                    <section class="glass-panel">
                        <div class="panel-title">Live Data Stream</div>
                        <div id="engine-live-data">Waiting for stream...</div>
                    </section>
                    
                    <!-- RIGHT: Controls -->
                    <section class="glass-panel">
                        <div class="panel-title">Configuration</div>
                        <div class="control-group">
                            <label>Leverage</label>
                            <input type="range" min="1" max="10" value="1">
                        </div>
                    </section>
                </div>
            </div>
        `;
    }

    async init() {
        console.log(`[EnginePage] Initialized ${this.engineId}`);
        // Subscribe to high-frequency websocket channel for this engine
        // window.socket.send({ action: 'subscribe', channel: this.engineId });
    }

    async destroy() {
        console.log(`[EnginePage] Destroying ${this.engineId}`);
        // Unsubscribe
        // window.socket.send({ action: 'unsubscribe', channel: this.engineId });
    }
}
