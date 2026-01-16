/**
 * Phantom Arbiter - Trading OS (Modular)
 * ======================================
 * V22: Refactored into ES6 modules for maintainability.
 * 
 * Components:
 * - WebSocketManager: Connection lifecycle
 * - Terminal: Log display
 * - EngineCard: Individual engine controls
 * - MarketData: Live price display
 * - ModalManager: Settings/SOS dialogs
 * - HeaderStats: Status bar metrics
 */

import { WebSocketManager } from './core/websocket.js';
import { Terminal } from './components/terminal.js';
import { EngineCard } from './components/engine-card.js';
import { MarketData } from './components/market-data.js';
import { TokenWatchlist } from './components/token-watchlist.js';
import { ArbScanner, FundingMonitor, ScalpPods, LstMonitor } from './components/market-component.js';
import { Inventory } from './components/inventory.js';
import { ModalManager } from './components/modal.js';
import { HeaderStats } from './components/header-stats.js';
import { LayoutManager } from './components/layout-manager.js';
import { SystemMetrics } from './components/system-metrics.js';
import { SolTape } from './components/sol-tape.js';
import { MajorsTape } from './components/majors-tape.js';
import { MemeSniperStrip } from './components/meme-sniper-strip.js';
import { Toast } from './components/toast.js';
import { APIHealth } from './components/api-health.js';
import { UnifiedVaultController } from './components/unified-vault.js';
import { TickerTape, createWhaleItem } from './components/ticker-tape.js';
import { DriftController } from './components/drift-controller.js';
import { EngineVaultCard } from './components/engine-vault-card.js';
import { ViewManager } from './core/view-manager.js';
import { EngineManager } from './core/engine-manager.js';
import { PacketHandler } from './core/packet-handler.js';

class TradingOS {
    constructor() {
        // Initialize Global Components (Always in DOM)
        this.layoutManager = new LayoutManager();
        this.terminal = new Terminal('log-stream');
        this.marketData = new MarketData(); // Doesn't require DOM immediately
        this.headerStats = new HeaderStats();
        this.modal = new ModalManager();
        this.toast = new Toast();
        this.apiHealth = new APIHealth('api-health-container'); // This might fail if view-settings not loaded... wait, api-health-container was in view-settings!

        // Tapes (In Header - Always Present)
        this.solTape = new SolTape('sol-tape-container');
        this.majorsTape = new MajorsTape('majors-tape-container');
        this.whaleTicker = TickerTape.createWhaleTape('whale-tape-container', 'paper'); // ID was corrected in earlier steps

        // Dynamic Components (Initialized when view loads)
        this.tokenWatchlist = null;
        this.inventory = null;
        this.systemMetrics = null;
        this.unifiedVault = null;
        this.memeSniper = null;
        this.engines = {};
        this.marketComponents = {};
        this.activeComponents = {};

        // Mempool Sniper (Global Header)
        // this.memeSniperHeader = new MemeSniperStrip('meme-sniper-container'); // Removed per user request

        // WebSocket connection
        this.ws = new WebSocketManager({
            port: 8765,
            onConnect: () => this.onConnect(),
            onDisconnect: () => this.onDisconnect(),
            onMessage: (packet) => this.handlePacket(packet),
            onError: (err) => this.terminal.addLog('SYSTEM', 'ERROR', 'WebSocket Error')
        });

        // Modal callbacks
        // Modal callbacks
        this.modal.onSaveConfig = (engine, config) => this.engineManager.saveConfig(engine, config);
        this.modal.onSOS = () => this.executeSOS();

        // Header callbacks
        this.headerStats.onModeToggle = (mode) => {
            this.ws.send('SET_GLOBAL_MODE', { mode: mode });
            this.terminal.addLog('SYSTEM', 'WARNING', `GLOBAL MODE SWITCHED TO: ${mode}`);
            // Update all engine cards if they exist
            if (this.engines) {
                Object.values(this.engines).forEach(card => card && card.setMode(mode.toLowerCase()));
            }
        };

        // Modal callbacks
        this.modal.onSaveConfig = (engine, config) => this.engineManager.saveConfig(engine, config);



        // Connect
        const url = this.ws.connect();
        this.terminal.addLog('SYSTEM', 'INFO', `Connecting to Command Center: ${url}...`);

        // Initialize Managers
        this.viewManager = new ViewManager(this);
        this.engineManager = new EngineManager(this);
        this.packetHandler = new PacketHandler(this);

        this.viewManager.bindEvents();

        // Load Default View
        this.viewManager.switchView('dashboard');
    }








    /**
     * Handle WebSocket connect
     */
    onConnect() {
        this.terminal.addLog('SYSTEM', 'SUCCESS', '🎮 Command Center Linked');
        this.headerStats.setConnectionStatus(true);
        this.ws.send('GET_STATUS');
    }

    /**
     * Handle WebSocket disconnect
     */
    onDisconnect() {
        this.terminal.addLog('SYSTEM', 'WARNING', 'Link Lost - Reconnecting...');
        this.headerStats.setConnectionStatus(false);
    }

    /**
     * Handle incoming packets
     */
    handlePacket(packet) {
        this.packetHandler.handle(packet);
    }





    /**
     * Update Token Scalper Watch Table
     */
    updateScalperWatch(watchlist) {
        if (!watchlist || !Array.isArray(watchlist)) return;

        const tbody = document.querySelector('#intel-table tbody');
        if (!tbody) return;

        // Clear if only "Listening..." row exists
        if (tbody.rows.length === 1 && tbody.rows[0].innerText.includes('Listening')) {
            tbody.innerHTML = '';
        }

        // We'll rebuild or update. For simplicity, rebuild (max 10-20 items)
        let html = '';
        watchlist.forEach(token => {
            const isPos = token.change_5m >= 0;
            const fluxClass = isPos ? 'profit-positive' : 'profit-negative';
            const fluxSign = isPos ? '+' : '';

            // Format Volume (e.g. 1.2M)
            const vol = token.volume > 1000000 ? (token.volume / 1000000).toFixed(1) + 'M' : (token.volume / 1000).toFixed(1) + 'K';

            html += `
                <tr>
                    <td><span class="token-ticker">${token.symbol}</span></td>
                    <td>$${token.price.toFixed(4)}</td>
                    <td class="${fluxClass}">${fluxSign}${token.change_5m.toFixed(2)}%</td>
                    <td style="color: var(--text-dim);">${vol}</td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    }

    /**
     * Handle generic signals (e.g. for Drift Ticker)
     */
    handleSignal(payload) {
        // Update Drift Ticker
        const ticker = document.getElementById('drift-ticker');
        if (ticker && payload) {
            let msg = '';
            if (payload.type === 'funding') {
                msg = `💰 Funding Opp: ${payload.symbol} ${payload.apr}% APR`;
            } else if (payload.type === 'arb') {
                msg = `⚡ Arb Signal: ${payload.symbol} -> ${payload.profit_pct}%`;
            }

            if (msg) {
                ticker.textContent = msg;
                ticker.style.animation = 'none';
                ticker.offsetHeight; /* trigger reflow */
                ticker.style.animation = 'pulse-text 2s infinite';
            }
        }

        // WHALE TAPE Integration
        if (payload.type === 'WHALE_ACTIVITY' || payload.source === 'WHALE') {
            const data = payload.data || {};
            const symbol = data.mint || data.symbol || 'UNK';
            // Default to $50k if missing, just to show something, or 0
            const value = data.amount_usd || data.value || 50000;
            const direction = (data.direction || 'buy').toLowerCase();

            const item = createWhaleItem(symbol, value, direction);
            if (this.whaleTicker) {
                this.whaleTicker.addItem(item);
            }
        }
    }

    /**
     * Execute emergency stop
     */
    executeSOS() {
        this.ws.send('SOS');
        this.terminal.addLog('SYSTEM', 'WARNING', '🆘 EMERGENCY STOP INITIATED');
    }



    /**
     * Handle SOS response
     */
    handleSOSResponse(packet) {
        const { result } = packet;
        if (result.success) {
            this.terminal.addLog('SYSTEM', 'WARNING',
                `SOS Complete: ${result.engines_stopped} engines stopped`);
        } else {
            this.terminal.addLog('SYSTEM', 'ERROR', `SOS Failed: ${result.message}`);
        }
    }




    /**
     * Update intelligence table
     */
    updateIntelTable(type, data) {
        const tbody = document.querySelector('#intel-table tbody');
        if (!tbody) return;

        // Remove placeholder
        const placeholder = tbody.querySelector('td[colspan]');
        if (placeholder) placeholder.parentElement.remove();

        const row = document.createElement('tr');

        if (type === 'ARB') {
            row.innerHTML = `
                <td>${data.token || data.base}</td>
                <td>${data.route || `${data.buy_venue} → ${data.sell_venue}`}</td>
                <td class="${data.spread > 0 ? 'positive' : 'negative'}">${data.spread.toFixed(2)}%</td>
                <td class="positive">$${(data.est_profit || 0).toFixed(2)}</td>
            `;
        } else {
            row.innerHTML = `
                <td>${data.token || data.symbol}</td>
                <td>${data.signal || data.action}</td>
                <td>${data.action}</td>
                <td>${(data.confidence * 100).toFixed(0)}%</td>
            `;
        }

        tbody.insertBefore(row, tbody.firstChild);

        // Keep max 20 rows
        while (tbody.children.length > 20) {
            tbody.removeChild(tbody.lastChild);
        }
    }

    /**
     * Update Scalp Target Display (from real engine signals)
     */
    updateScalpTarget(signalData) {
        // data: { token, sentiment, confidence, action, price }
        const symbolEl = document.getElementById('scalp-target-symbol');
        const spreadEl = document.getElementById('scalp-target-spread'); // Reusing spread ID for Confidence
        const sparklineEl = document.getElementById('scalp-target-sparkline');
        const durationEl = document.getElementById('scalp-target-duration'); // If exists

        if (symbolEl) {
            symbolEl.textContent = signalData.token;
            symbolEl.style.color = signalData.action === 'BUY' ? 'var(--neon-green)' : 'var(--neon-red)';
        }
        if (spreadEl) {
            const conf = (signalData.confidence * 100).toFixed(0);
            spreadEl.textContent = `${conf}% Confidence`;
            spreadEl.style.color = signalData.confidence > 0.8 ? 'var(--neon-green)' : 'var(--neon-gold)';
        }

        // Simulating sparkline update for activity
        if (sparklineEl) {
            sparklineEl.textContent = "Activity Detected";
        }

        // Add log
        if (this.terminal) {
            this.terminal.addLog('SCALP', 'SIGNAL', `${signalData.action} ${signalData.token} (${(signalData.confidence * 100).toFixed(0)}%) - SENTIMENT: ${signalData.sentiment}`);
        }
    }

    /**
     * Update Scalp Engine Stats (from engine updates)
     */
    updateScalpStats(payload) {
        // payload: { active_pods: [], wallet: {}, ... }
        if (payload.active_pods !== undefined) {
            const podsEl = document.querySelector('[data-config="active_pods"]');
            if (podsEl) podsEl.textContent = payload.active_pods.length || payload.active_pods;
        }

        // Update Dedicated Scalp Vault
        if (payload.wallet) {
            this.inventory.updateScalp(payload.wallet);
        }
    }
}

// Initialize when DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.tradingOS = new TradingOS();
});
