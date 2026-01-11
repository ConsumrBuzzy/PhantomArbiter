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
import { APIHealth } from './components/api-health.js';
import { UnifiedVaultController } from './components/unified-vault.js';
import { TickerTape, createWhaleItem } from './components/ticker-tape.js';

// Router & Pages
import { Router } from './core/router.js';
import { DashboardPage } from './pages/dashboard-page.js';
import { EnginePage } from './pages/engine-page.js';
import { PacketHandler } from './core/packet-handler.js';

class TradingOS {
    constructor() {
        // Initialize components
        this.layoutManager = new LayoutManager();
        this.terminal = new Terminal('log-stream');
        this.marketData = new MarketData();

        // Initialize Router
        this.router = new Router('app-root');

        // Register Routes
        this.router.register('/dashboard', new DashboardPage('dashboard'));
        this.router.register('/engine/arb', new EnginePage('arb'));
        this.router.register('/engine/funding', new EnginePage('funding'));
        this.router.register('/engine/scalp', new EnginePage('scalp'));
        this.router.register('/engine/drift', new EnginePage('drift')); // Future dedicated page
        // Default route is handled by Router._handleHashChange

        this.tokenWatchlist = new TokenWatchlist('watchlist-panel'); // Note: Watchlist panel ID might only exist in DashboardPage now?
        // Watchlist panel is inside DashboardPage, so this initialization might fail if it runs before mount.
        // However, TokenWatchlist likely binds on init. If element missing, it might error.
        // We will defer legacy component init if possible, or accept warning. 
        // For V1, the dashboard mounts immediately on load, so it might race.
        // Ideally, TokenWatchlist should be part of DashboardPage init().

        // Global Services
        this.inventory = new Inventory('inventory-table'); // Same issue: ID in sub-page.
        this.headerStats = new HeaderStats();
        this.modal = new ModalManager();
        // Remove legacy WhaleTape (replaced by TickerTape in header)

        this.modal = new ModalManager();
        this.systemMetrics = new SystemMetrics('chart-metrics');
        this.solTape = new SolTape('sol-tape-container');
        this.toast = new Toast();
        this.apiHealth = new APIHealth('api-health-container');

        // NEW: Design System Components
        this.unifiedVault = new UnifiedVaultController('unified-vault-container');
        this.majorsTape = new MajorsTape('majors-tape-container');
        this.whaleTicker = TickerTape.createWhaleTape('whale-tape-header-mount', 'paper');

        // Meme Sniper in Main View (replacing old Whale location)
        this.memeSniper = new MemeSniperStrip('meme-sniper-mount');

        // Wire bridge button
        // this.wireBridgeButton(); // Legacy

        // Component Registry for Router
        this.activeComponents = {};
        this.activeComponents = {};
        this.unifiedVault.setBridgeCallback((amount) => {
            this.ws.send('BRIDGE_TRIGGER', { amount });
            this.terminal.addLog('BRIDGE', 'INFO', `Bridge initiated: $${amount.toFixed(2)} USDC → Phantom`);
        });

        // Engine cards
        this.engines = {
            arb: new EngineCard('arb', {
                onToggle: (name, status, mode) => this.toggleEngine(name, status, mode),
                onSettings: (name, config) => this.modal.openSettings(name, config),
                onModeChange: (name, mode) => this.terminal.addLog('SYSTEM', 'INFO',
                    `${name} mode set to ${mode.toUpperCase()}`)
            }),
            funding: new EngineCard('funding', {
                onToggle: (name, status, mode) => this.toggleEngine(name, status, mode),
                onSettings: (name, config) => this.modal.openSettings(name, config),
                onModeChange: (name, mode) => this.terminal.addLog('SYSTEM', 'INFO',
                    `${name} mode set to ${mode.toUpperCase()}`)
            }),
            scalp: new EngineCard('scalp', {
                onToggle: (name, status, mode) => this.toggleEngine(name, status, mode),
                onSettings: (name, config) => this.modal.openSettings(name, config),
                onModeChange: (name, mode) => this.terminal.addLog('SYSTEM', 'INFO',
                    `${name} mode set to ${mode.toUpperCase()}`)
            }),
            lst: new EngineCard('lst', {
                onToggle: (name, status, mode) => this.toggleEngine(name, status, mode),
                onSettings: (name, config) => this.modal.openSettings(name, config),
                onModeChange: (name, mode) => this.terminal.addLog('SYSTEM', 'INFO',
                    `${name} mode set to ${mode.toUpperCase()}`)
            })
        };

        // Market Components (Specialized Views)
        this.marketComponents = {
            arb: new ArbScanner('arb'),
            funding: new FundingMonitor('funding'),
            scalp: new ScalpPods('scalp'),
            lst: new LstMonitor('lst')
        };

        // WebSocket connection
        this.ws = new WebSocketManager({
            port: 8765,
            onConnect: () => this.onConnect(),
            onDisconnect: () => this.onDisconnect(),
            onMessage: (packet) => this.packetHandler.handle(packet),
            onError: (err) => this.terminal.addLog('SYSTEM', 'ERROR', 'WebSocket Error')
        });

        // Initialize PacketHandler
        this.packetHandler = new PacketHandler(this);

        // Modal callbacks
        this.modal.onSaveConfig = (engine, config) => this.saveConfig(engine, config);
        this.modal.onSOS = () => this.executeSOS();

        // Header callbacks
        this.headerStats.onModeToggle = (mode) => {
            this.ws.send('SET_GLOBAL_MODE', { mode: mode });
            this.terminal.addLog('SYSTEM', 'WARNING', `GLOBAL MODE SWITCHED TO: ${mode}`);

            // Update all engine cards to match default if not manually overridden
            Object.values(this.engines).forEach(card => card.setMode(mode.toLowerCase()));
        };

        // Bind navigation and SOS
        this.bindGlobalEvents();

        // Connect
        const url = this.ws.connect();
        this.terminal.addLog('SYSTEM', 'INFO', `Connecting to Command Center: ${url}...`);
    }

    registerDashboardComponents(components) {
        this.activeComponents = components;
        // Trigger immediate update if cache exists
        if (this.lastData) {
            this.handlePacket(this.lastData);
        }
    }

    unregisterDashboardComponents() {
        this.activeComponents = {};
    }

    /**
     * Bind global UI events (navigation, SOS)
     */
    bindGlobalEvents() {
        // Navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            // Update valid sidebar links to use hash
            // The HTML still uses data-view="dashboard", etc.
            // We will interpret click -> hash
            item.addEventListener('click', () => {
                const view = item.dataset.view || item.dataset.tooltip?.toLowerCase(); // Fallback to tooltip if data-view missing
                if (view) {
                    // Map legacy view names to routes
                    const routeMap = {
                        'dashboard': '/dashboard',
                        'scanner': '/engine/arb', // Example mapping
                        'engines': '/engine/funding',
                        'settings': '/config'
                    };

                    // Fallback for font-awesome icons that might not have data-view matches from the revert
                    let target = routeMap[view] || '/dashboard';
                    // Specific checks for sidebar structure (user reverted sidebar uses icons)
                    if (view.includes('Dashboard')) target = '/dashboard';
                    if (view.includes('Analytics')) target = '/engine/arb'; // Placeholder

                    window.location.hash = target;
                }
            });
        });

        // Listen for navigation events from existing cards
        Object.values(this.engines).forEach(engine => {
            engine.card.addEventListener('engine-selected', (e) => {
                this.showEngineDetail(e.detail.engineId);
            });
        });

        // Initialize Detail View Back Button
        const backBtn = document.querySelector('.back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                this.showEngineList();
            });
        }
    }

    showEngineDetail(engineId) {
        console.log(`Navigating to Control Room: ${engineId}`);
        this.currentDetailEngine = engineId;

        // 1. Hide List
        document.querySelector('.engine-stack').style.display = 'none';

        // 2. Show Detail Container (CSS handles slide-in)
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
        const engineState = this.engines[engineId]?.state || {};
        const statusBadge = document.getElementById('detail-engine-status');
        if (statusBadge) {
            statusBadge.textContent = (engineState.status || 'stopped').toUpperCase();
            statusBadge.className = 'engine-badge ' + (engineState.status || 'stopped');
        }

        // 4. Request Engine Vault Data
        this.ws.send('GET_ENGINE_VAULT', { engine: engineId });

        // 5. Populate Config Panel
        this.populateConfigPanel(engineId);

        // 6. Bind Vault Control Buttons
        this.bindDetailViewEvents(engineId);

        // 7. Update Log Filter
        const logFilter = document.getElementById('detail-log-filter');
        if (logFilter) {
            logFilter.textContent = engineId.toUpperCase();
        }

        // 8. Update Inventory Context
        if (this.inventory) this.inventory.setContext(engineId);
    }

    /**
     * Populate config panel based on engine type
     */
    populateConfigPanel(engineId) {
        const configGrid = document.getElementById('detail-config-grid');
        if (!configGrid) return;

        const engine = this.engines[engineId];
        const config = engine?.state?.config || {};

        const configFormatters = {
            'arb': {
                'min_spread': { label: 'Min Spread', format: v => `${v}%` },
                'max_trade_usd': { label: 'Max Trade', format: v => `$${v}` },
                'scan_interval': { label: 'Scan Interval', format: v => `${v}s` },
                'risk_tier': { label: 'Risk Tier', format: v => v.toUpperCase() }
            },
            'funding': {
                'leverage': { label: 'Leverage', format: v => `${v}x` },
                'watchdog_threshold': { label: 'Watchdog', format: v => `${(v * 100).toFixed(2)}%` },
                'rebalance_enabled': { label: 'Rebalance', format: v => v ? 'ON' : 'OFF' },
                'max_position_usd': { label: 'Max Position', format: v => `$${v}` }
            },
            'scalp': {
                'take_profit_pct': { label: 'Take Profit', format: v => `+${v}%` },
                'stop_loss_pct': { label: 'Stop Loss', format: v => `-${v}%` },
                'max_pods': { label: 'Max Pods', format: v => v },
                'sentiment_threshold': { label: 'Sentiment', format: v => `${(v * 100).toFixed(0)}%` }
            },
            'lst': {
                'peg_threshold': { label: 'Peg Threshold', format: v => `${v}%` },
                'exit_liquidity': { label: 'Exit Check', format: v => v ? 'ON' : 'OFF' }
            }
        };

        const formatters = configFormatters[engineId] || {};
        let html = '';

        Object.entries(config).forEach(([key, value]) => {
            const formatter = formatters[key];
            if (formatter) {
                html += `
                    <div class="config-item">
                        <div class="config-label">${formatter.label}</div>
                        <div class="config-value">${formatter.format(value)}</div>
                    </div>
                `;
            }
        });

        // Fallback if no config
        if (!html) {
            html = '<div class="config-item"><div class="config-label">No Config</div><div class="config-value">--</div></div>';
        }

        configGrid.innerHTML = html;
    }

    /**
     * Bind vault control button events
     */
    bindDetailViewEvents(engineId) {
        // Reset Sim Button
        const resetBtn = document.querySelector('.vault-btn.reset');
        if (resetBtn) {
            resetBtn.onclick = () => {
                this.ws.send('VAULT_RESET', { engine: engineId });
                this.terminal.addLog('VAULT', 'WARNING', `Resetting ${engineId} vault...`);
            };
        }

        // Live Sync Button
        const syncBtn = document.querySelector('.vault-btn.sync');
        if (syncBtn) {
            syncBtn.onclick = () => {
                this.ws.send('VAULT_SYNC', { engine: engineId });
                this.terminal.addLog('VAULT', 'INFO', `Syncing ${engineId} vault from live wallet...`);
            };
        }

        // Power Toggle in Detail View
        const powerBtn = document.querySelector('.detail-power');
        if (powerBtn) {
            powerBtn.onclick = () => {
                const engine = this.engines[engineId];
                const mode = engine?.mode || 'paper';
                const status = engine?.state?.status || 'stopped';
                this.toggleEngine(engineId, status, mode);
            };
        }

        // Mode Selector in Detail View
        const modeSelector = document.querySelector('.detail-mode');
        if (modeSelector) {
            modeSelector.querySelectorAll('.mode-btn').forEach(btn => {
                btn.onclick = () => {
                    modeSelector.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    if (this.engines[engineId]) {
                        this.engines[engineId].setMode(btn.dataset.mode);
                    }
                };
            });
        }
    }

    /**
     * Update vault panel with data from WebSocket
     */


    /**
     * Add log entry to engine-specific log stream
     */
    addEngineLog(engineId, level, message) {
        if (this.currentDetailEngine !== engineId) return;

        const logStream = document.getElementById('detail-log-stream');
        if (!logStream) return;

        // Clear placeholder if first real log
        if (logStream.querySelector('.log-entry.info')?.textContent.includes('Waiting')) {
            logStream.innerHTML = '';
        }

        const entry = document.createElement('div');
        entry.className = `log-entry ${level.toLowerCase()}`;
        entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        logStream.insertBefore(entry, logStream.firstChild);

        // Keep max 50 entries
        while (logStream.children.length > 50) {
            logStream.removeChild(logStream.lastChild);
        }
    }

    showEngineList() {
        // 1. Hide Detail
        const detailView = document.getElementById('view-engine-detail');
        detailView.classList.remove('active');

        // 2. Show List
        document.querySelector('.engine-stack').style.display = 'flex';

        // Reset Inventory Context
        if (this.inventory) this.inventory.setContext('GLOBAL');
    }

    initializeWebSocket() {
        document.getElementById('sos-btn')?.addEventListener('click', () => {
            this.modal.openSOS();
        });
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
     * Toggle engine on/off
     */
    toggleEngine(engineName, currentStatus, mode) {
        const isRunning = currentStatus === 'running' || currentStatus === 'starting';

        if (isRunning) {
            this.ws.send('STOP_ENGINE', { engine: engineName });
            this.terminal.addLog('SYSTEM', 'INFO', `Stopping ${engineName} engine...`);
        } else {
            this.ws.send('START_ENGINE', { engine: engineName, mode: mode });
            this.terminal.addLog('SYSTEM', 'INFO',
                `Starting ${engineName} engine in ${mode.toUpperCase()} mode...`);
        }
    }

    /**
     * Save engine configuration
     */
    saveConfig(engineName, config) {
        this.ws.send('UPDATE_CONFIG', { engine: engineName, config });
        this.terminal.addLog('SYSTEM', 'INFO', `Updated config for ${engineName}`);
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


    /**
     * Execute emergency stop
     */
    executeSOS() {
        this.ws.send('SOS');
        this.terminal.addLog('SYSTEM', 'WARNING', '🆘 EMERGENCY STOP INITIATED');
    }

    /**
     * Handle engine response
     */


    /**
     * Switch between views
     */
    switchView(viewName) {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.view === viewName);
        });

        document.querySelectorAll('.view-panel').forEach(panel => {
            panel.classList.toggle('active', panel.id === `view-${viewName}`);
        });

        // V23.0: Request API health when entering Config view
        if (viewName === 'config' && this.ws) {
            this.ws.send('GET_API_HEALTH', {});
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
}

// Initialize when DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.tradingOS = new TradingOS();
});
