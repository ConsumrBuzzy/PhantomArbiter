import { UnifiedVaultController } from '../components/unified-vault.js';
import { Inventory } from '../components/inventory.js';
import { SystemMetrics } from '../components/system-metrics.js';
import { MemeSniperStrip } from '../components/meme-sniper-strip.js';
import { EngineCard } from '../components/engine-card.js';
import { ArbScanner, FundingMonitor } from '../components/market-component.js';
import { APIHealth } from '../components/api-health.js';
import { DriftController } from '../components/drift-controller.js';
import { EngineVaultCard } from '../components/engine-vault-card.js';
import { TokenWatchlist } from '../components/token-watchlist.js';
import { createWhaleItem } from '../components/ticker-tape.js';

/**
 * ViewManager
 * ===========
 * Handles all view switching, dynamic component loading, and navigation logic.
 */
export class ViewManager {
    constructor(app) {
        this.app = app; // Reference to main TradingOS instance
        this.activeComponents = {}; // ViewManager specific local cache if needed, but we rely on app for shared state logic mostly. 
        // Actually, let's remove local initialization if we want to rely on app.
        // But for safety, let's just leave it commented or remove it to avoid confusion.
        this.currentDetailEngine = null;

        // Cache DOM elements
        this.viewStack = document.querySelector('.view-stack');
        this.navItems = document.querySelectorAll('.nav-item');
    }

    /**
     * Bind global navigation events
     */
    bindEvents() {
        // Main Navigation
        this.navItems.forEach(item => {
            item.addEventListener('click', () => this.switchView(item.dataset.view));
        });

        // Detail View Back Button
        const backBtn = document.querySelector('.back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                this.showEngineList();
            });
        }

        // SOS Button
        const sosBtn = document.getElementById('sos-btn');
        if (sosBtn) {
            sosBtn.addEventListener('click', () => {
                if (this.app.modal) this.app.modal.openSOS();
            });
        }
    }

    /**
     * Switch between views (Async Template Loading)
     */
    async switchView(viewName) {
        const viewId = `view-${viewName}`;
        let viewPanel = document.getElementById(viewId);

        // Update Nav State
        this.navItems.forEach(item => {
            item.classList.toggle('active', item.dataset.view === viewName);
        });

        // Dynamic Loading if not exists
        if (!viewPanel) {
            try {
                console.log(`[ViewManager] Loading template: templates/${viewName}.html`);
                const response = await fetch(`templates/${viewName}.html`);

                if (response.ok) {
                    const html = await response.text();

                    // Create view container
                    viewPanel = document.createElement('div');
                    viewPanel.className = 'view-panel';
                    viewPanel.id = viewId;
                    viewPanel.innerHTML = html;

                    this.viewStack.appendChild(viewPanel);

                    // Initialize newly loaded components
                    this.initializeDynamicComponents(viewName);
                } else {
                    console.error(`[ViewManager] Template ${viewName} not found`);
                }
            } catch (e) {
                console.error('[ViewManager] View load error:', e);
            }
        }

        // Toggle Visibility
        document.querySelectorAll('.view-panel').forEach(panel => {
            panel.classList.toggle('active', panel.id === viewId);
        });

        // Request API health when entering Config view
        if (viewName === 'settings' && this.app.ws) {
            this.app.ws.send('GET_API_HEALTH', {});
        }
    }

    /**
     * Initialize components appearing in dynamic views
     */
    initializeDynamicComponents(viewName) {
        console.log(`[ViewManager] Initializing components for ${viewName}`);
        if (this.app.layoutManager) this.app.layoutManager.refresh();

        if (viewName === 'dashboard') {
            this._initDashboardComponents();
        } else if (viewName.startsWith('engine-')) {
            const engineId = viewName.replace('engine-', '');
            if (engineId === 'drift') {
                this._initDriftEnginePage();
            }
        } else if (viewName === 'settings') {
            this._initSettingsComponents();
        } else if (viewName === 'scanner') {
            this._initScannerComponents();
        }
    }

    _initDashboardComponents() {
        try {
            // Initialize Dashboard Components
            console.log('[ViewManager] Creating UnifiedVaultController...');
            this.app.unifiedVault = new UnifiedVaultController('unified-vault-container');
            this.app.inventory = new Inventory();
            this.app.systemMetrics = new SystemMetrics('chart-metrics');
            this.app.memeSniper = new MemeSniperStrip('meme-sniper-mount'); // Dashboard Instance
            console.log('[ViewManager] Creating TokenWatchlist...');
            try {
                this.app.tokenWatchlist = new TokenWatchlist('watchlist-container');
            } catch (e) { console.error('[ViewManager] Watchlist Init Error:', e); }

            // Active Scalp Engine Card (Dashboard Widget)
            const scalpWidget = new EngineCard('scalp', {
                onToggle: (n, s, m) => this.app.engineManager.toggleEngine(n, s, m),
                onSettings: (n, c) => this.app.engineManager.openSettings(n, c),
                onModeChange: (n, m) => { if (this.app.engines[n]) this.app.engines[n].setMode(m); }
            });
            this.app.engines['scalp'] = scalpWidget;
            this.app.scalpEngineWidget = scalpWidget;

            if (this.app.unifiedVault) {
                this.app.unifiedVault.setBridgeCallback((amount) => {
                    this.app.ws.send('BRIDGE_TRIGGER', { amount });
                    this.app.terminal.addLog('BRIDGE', 'INFO', `Bridge initiated: $${amount.toFixed(2)} USDC -> Phantom`);
                });
            }

            this.registerDashboardComponents({
                vault: this.app.unifiedVault,
                inventory: this.app.inventory,
                metrics: this.app.systemMetrics,
                sniper: this.app.memeSniper
            });

            // Request Initial Data
            if (this.app.ws && this.app.ws.connected) {
                this.app.ws.send('GET_SYSTEM_STATS', {});
                this.app.ws.send('GET_WATCHLIST', {});
            }
        } catch (e) {
            console.error("[ViewManager] Error initializing dashboard components:", e);
        }
    }

    _initSettingsComponents() {
        try {
            this.app.apiHealth = new APIHealth('api-health-container');
            // Request initial health data
            if (this.app.ws && this.app.ws.connected) this.app.ws.send('GET_API_HEALTH', {});
        } catch (e) {
            console.error("[ViewManager] Error initializing settings components:", e);
        }
    }

    _initScannerComponents() {
        try {
            this.app.marketComponents['arb'] = new ArbScanner('arb', '#arb-scanner-mount');
            this.app.marketComponents['funding'] = new FundingMonitor('funding', '#funding-scanner-mount');
        } catch (e) {
            console.error("[ViewManager] Error initializing scanner components:", e);
        }
    }

    _initDriftEnginePage() {
        console.log('[ViewManager] Initializing Drift Engine page');

        // 1. Initialize Drift Controller
        this.app.driftController = new DriftController();
        this.app.driftController.init();

        // 2. Initialize Drift Vault Card
        const sideCol = document.querySelector('.grid-col-side');
        if (sideCol) {
            let vaultContainer = document.getElementById('drift-vault-card-container');
            if (!vaultContainer) {
                vaultContainer = document.createElement('div');
                vaultContainer.id = 'drift-vault-card-container';
                const controlPanel = sideCol.querySelector('section:first-child');
                if (controlPanel) controlPanel.after(vaultContainer);
            }
            this.app.driftVault = new EngineVaultCard('drift-vault-card-container', 'Drift');
        }

        // Bind engine control buttons (Generic Start/Stop)
        const controlMount = document.getElementById('drift-control-card-mount');
        if (controlMount && !this.app.engines['drift']) {
            this.app.engines['drift'] = new EngineCard('drift', {
                onToggle: (n, s, m) => this.app.engineManager.toggleEngine(n, s, m),
                onSettings: (n, c) => this.app.engineManager.openSettings(n, c),
                onModeChange: (n, m) => { if (this.app.engines[n]) this.app.engines[n].setMode(m); }
            });
        }

        // Settle PnL button
        const settlePnlBtn = document.getElementById('drift-settle-pnl-btn');
        if (settlePnlBtn) {
            settlePnlBtn.onclick = () => {
                this.app.ws.send('DRIFT_SETTLE_PNL', {});
                this.app.terminal.addLog('DRIFT', 'INFO', 'Settling PnL...');
            };
        }

        // Close All button
        const closeAllBtn = document.getElementById('drift-close-all-btn');
        if (closeAllBtn) {
            closeAllBtn.onclick = () => {
                if (confirm('Close ALL Drift positions?')) {
                    this.app.ws.send('DRIFT_CLOSE_ALL', {});
                    this.app.terminal.addLog('DRIFT', 'WARNING', 'Closing all positions...');
                }
            };
        }

        // Refresh Markets button
        const refreshBtn = document.getElementById('drift-refresh-markets-btn');
        if (refreshBtn) {
            refreshBtn.onclick = () => {
                const icon = refreshBtn.querySelector('.fa-sync');
                if (icon) icon.classList.add('spinning');
                if (this.app.fetchDriftMarketData) {
                    this.app.fetchDriftMarketData().then(() => {
                        setTimeout(() => icon?.classList.remove('spinning'), 500);
                    });
                }
            };
        }

        // Request initial state
        if (this.app.ws && this.app.ws.connected) {
            this.app.ws.send('GET_SYSTEM_STATS', {});
            this.app.ws.send('GET_DRIFT_MARKETS', {});
        }

        if (this.app.fetchDriftMarketData) {
            this.app.fetchDriftMarketData();
        }
    }

    registerDashboardComponents(components) {
        this.app.activeComponents = components;
        // Trigger immediate update if cache exists
        if (this.app.lastData) {
            try {
                this.app.handlePacket(this.app.lastData);
            } catch (e) {
                console.warn("[ViewManager] Skipped replay packet due to init state", e);
            }
        }
    }

    unregisterDashboardComponents() {
        this.app.activeComponents = {};
    }

    showEngineDetail(engineId) {
        console.log(`[ViewManager] Navigating to Control Room: ${engineId}`);
        this.currentDetailEngine = engineId;

        // 1. Hide List
        document.querySelector('.engine-stack').style.display = 'none';

        // 2. Show Detail Container
        const detailView = document.getElementById('view-engine-detail');
        detailView.classList.add('active');

        // 3. Update Header
        const engineNames = {
            'arb': 'Arbitrage Engine',
            'funding': 'Funding Rate Engine',
            'scalp': 'Scalp Sniper Engine',
            'lst': 'LST De-Pegger'
        };
        document.getElementById('detail-engine-name').textContent = engineNames[engineId] || engineId.toUpperCase();

        // Update status badge
        const engineState = this.app.engines[engineId]?.state || {};
        const statusBadge = document.getElementById('detail-engine-status');
        if (statusBadge) {
            statusBadge.textContent = (engineState.status || 'stopped').toUpperCase();
            statusBadge.className = 'engine-badge ' + (engineState.status || 'stopped');
        }

        // 4. Delegate to EngineManager (if available) or App
        if (this.app.ws) {
            this.app.ws.send('GET_ENGINE_VAULT', { engine: engineId });
        }

        if (this.app.populateConfigPanel) {
            this.app.populateConfigPanel(engineId);
        } else if (this.app.engineManager) {
            this.app.engineManager.populateConfigPanel(engineId);
        }

        if (this.app.bindDetailViewEvents) {
            this.app.bindDetailViewEvents(engineId);
        } else if (this.app.engineManager) {
            this.app.engineManager.bindEngineControls(engineId);
        }

        // 7. Update Log Filter
        const logFilter = document.getElementById('detail-log-filter');
        if (logFilter) {
            logFilter.textContent = engineId.toUpperCase();
        }

        // 8. Update Inventory Context
        if (this.app.inventory) this.app.inventory.setContext(engineId);
    }

    showEngineList() {
        // 1. Hide Detail
        const detailView = document.getElementById('view-engine-detail');
        detailView.classList.remove('active');

        // 2. Show List
        document.querySelector('.engine-stack').style.display = 'flex';

        // Reset Inventory Context
        if (this.app.inventory) this.app.inventory.setContext('GLOBAL');
        this.currentDetailEngine = null;
    }

    // ═══════════════════════════════════════════════════════════════
    // UI UPDATES (Moved from App)
    // ═══════════════════════════════════════════════════════════════

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
            if (this.app.whaleTicker) {
                this.app.whaleTicker.addItem(item);
            }
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
        if (this.app.terminal) {
            this.app.terminal.addLog('SCALP', 'SIGNAL', `${signalData.action} ${signalData.token} (${(signalData.confidence * 100).toFixed(0)}%) - SENTIMENT: ${signalData.sentiment}`);
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
        if (payload.wallet && this.app.inventory) {
            this.app.inventory.updateScalp(payload.wallet);
        }
    }
}
