import { BasePage } from '../core/base-page.js';
import { UnifiedVaultController } from '../components/unified-vault.js';
import { MemeSniperStrip } from '../components/meme-sniper-strip.js';
import { Inventory } from '../components/inventory.js';
import { TokenWatchlist } from '../components/token-watchlist.js';
import { SystemMetrics } from '../components/system-metrics.js';

export class DashboardPage extends BasePage {
    async render() {
        return `
            <div class="dashboard-split-view" style="display: grid; grid-template-columns: 1fr 1.2fr; gap: 20px; height: 100%; padding: 20px;">
                <!-- Header is now Global in index.html -->

                <div class="left-column">
                    <section id="unified-vault-container" class="unified-vault-mount"></section>
                    
                    <section class="glass-panel" id="inventory-panel">
                        <div class="panel-title">Inventory</div>
                        <div class="inventory-split">
                            <div class="inventory-half live">
                                <div class="inventory-label" style="color: var(--neon-red);">🔴 LIVE</div>
                                <table id="live-inventory-table"><thead><tr><th>ASSET</th><th>AMOUNT</th><th>VALUE</th></tr></thead><tbody><tr><td colspan="3">Loading...</td></tr></tbody></table>
                            </div>
                            <div class="inventory-half paper">
                                <div class="inventory-label" style="color: var(--neon-blue);">🔵 PAPER</div>
                                <table id="paper-inventory-table"><thead><tr><th>ASSET</th><th>AMOUNT</th><th>VALUE</th></tr></thead><tbody><tr><td colspan="3">Loading...</td></tr></tbody></table>
                            </div>
                        </div>
                    </section>
                </div>

                <div class="right-column">
                    <div id="meme-sniper-mount" class="glass-panel" style="height: 300px; padding: 0; overflow: hidden; margin-bottom: 20px;">
                        <div class="sniper-loading">🚀 Scraper View Initializing...</div>
                    </div>

                    <section class="drift-vault-card" id="drift-panel">
                        <div class="drift-header">
                            <div class="drift-logo"><span>🌊 DRIFT PROTOCOL</span></div>
                            <div class="drift-status-badge">MAINNET</div>
                        </div>
                        <div class="drift-stats-grid">
                            <div class="drift-stat"><span class="drift-label">EQUITY</span><span class="drift-value" id="drift-equity">$0.00</span></div>
                            <div class="drift-stat"><span class="drift-label">Unrealized PnL</span><span class="drift-value" id="drift-pnl">--</span></div>
                            <div class="drift-stat"><span class="drift-label">LEVERAGE</span><span class="drift-value" id="drift-leverage">0x</span></div>
                        </div>
                        <div class="drift-actions">
                            <button class="drift-btn" onclick="window.router.navigate('/engine/drift')">Full View ⛶</button>
                        </div>
                    </section>

                    <section class="glass-panel" id="metrics-panel">
                        <div class="panel-title">System Metrics</div>
                        <div id="chart-metrics" style="height: 100%; width: 100%;"></div>
                    </section>
                </div>
            </div>
        `;
    }

    async init() {
        // Initialize Components
        // Note: In a real SPA, we'd pass the global 'app' instance to get access to services
        // For now, we instantiate new controllers or attach to existing globals.

        // 1. Vault
        this.vault = new UnifiedVaultController('unified-vault-container');

        // 2. Inventory
        this.inventory = new Inventory('inventory-table'); // Note: ID needs match

        // 3. Sniper
        this.sniper = new MemeSniperStrip('meme-sniper-mount');

        // 4. Metrics
        this.metrics = new SystemMetrics('chart-metrics');

        // Hook up to global data stream (window.tradingOS.marketData)
        // This part requires strict wiring. To keep it simple for now, 
        // we'll rely on the existing app.module.js event hub if possible, 
        // OR we make these components self-subscribing.

        // IMPORTANT: The global app.module.js is currently pushing data to components.
        // We need to register this page's components with the global app.
        if (window.tradingOS) {
            window.tradingOS.registerDashboardComponents({
                vault: this.vault,
                inventory: this.inventory,
                sniper: this.sniper,
                metrics: this.metrics
            });
        }
    }

    async destroy() {
        // Unregister from global updates
        if (window.tradingOS) {
            window.tradingOS.unregisterDashboardComponents();
        }
    }
}
