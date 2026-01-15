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
        this.modal.onSaveConfig = (engine, config) => this.saveConfig(engine, config);
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

        // Bind navigation and SOS
        this.bindGlobalEvents();

        // Connect
        const url = this.ws.connect();
        this.terminal.addLog('SYSTEM', 'INFO', `Connecting to Command Center: ${url}...`);

        // Load Default View
        this.switchView('dashboard');
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
            item.addEventListener('click', () => this.switchView(item.dataset.view));
        });


        // Listen for navigation events from existing cards
        Object.values(this.engines).forEach(engine => {
            if (engine.card) {  // Only bind if card exists in DOM
                engine.card.addEventListener('engine-selected', (e) => {
                    this.showEngineDetail(e.detail.engineId);
                });
            }
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
    updateVaultPanel(engineId, vaultData) {
        if (this.currentDetailEngine !== engineId) return;

        // Update equity
        const equityEl = document.getElementById('detail-vault-equity');
        if (equityEl) {
            equityEl.textContent = `$${(vaultData.equity || 0).toFixed(2)}`;
        }

        // Update asset rows
        const assetsContainer = document.getElementById('detail-vault-assets');
        if (assetsContainer && vaultData.assets) {
            let html = '';
            Object.entries(vaultData.assets).sort((a, b) => {
                // USDC first, then SOL, then others
                if (a[0] === 'USDC') return -1;
                if (b[0] === 'USDC') return 1;
                if (a[0] === 'SOL') return -1;
                if (b[0] === 'SOL') return 1;
                return 0;
            }).forEach(([asset, balance]) => {
                const displayBal = balance >= 1 ? balance.toFixed(2) : balance.toFixed(4);
                html += `
                    <div class="vault-asset-row">
                        <span class="vault-asset-symbol">${asset}</span>
                        <span class="vault-asset-balance">${displayBal}</span>
                    </div>
                `;
            });
            assetsContainer.innerHTML = html || '<div class="vault-asset-row"><span>No assets</span></div>';
        }
    }

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
        const { type, data } = packet;

        switch (type) {
            case 'SYSTEM_STATS':
                this.headerStats.update(data);
                if (data.live_wallet || data.paper_wallet) this.inventory.update(data);
                if (data.engines) this.updateEngineStates(data.engines);
                if (data.metrics) this.systemMetrics.update(data.metrics);

                // ═══════════════════════════════════════════════════════════════
                // UNIFIED BALANCE (Single Source of Truth)
                // ═══════════════════════════════════════════════════════════════
                if (data.unified_balance) {
                    // Update the UnifiedVaultController (Global or Page-Specific)
                    if (this.activeComponents.vault) {
                        this.activeComponents.vault.update(data.unified_balance);
                    } else if (this.unifiedVault) {
                        this.unifiedVault.update(data.unified_balance);
                    }

                    // Update Drift Panel (legacy support)
                    const driftEquity = data.unified_balance.drift?.equity || 0;
                    const equityEl = document.getElementById('drift-equity');
                    const pnlEl = document.getElementById('drift-pnl');

                    if (equityEl) equityEl.textContent = '$' + driftEquity.toFixed(2);
                    if (driftEquity > 0 && pnlEl) {
                        const pnl = data.unified_balance.drift?.pnl || 0;
                        pnlEl.textContent = (pnl >= 0 ? '+' : '') + '$' + Math.abs(pnl).toFixed(2);
                        pnlEl.className = 'drift-value ' + (pnl >= 0 ? 'positive' : 'negative');
                    }

                    // Update ticker mode based on global mode
                    if (data.mode && this.whaleTicker) {
                        this.whaleTicker.setMode(data.mode);
                    }
                }

                // Legacy CEX UI UPDATE (for backward compat)
                if (data.cex_wallet && !data.unified_balance) {
                    const cexBalEl = document.getElementById('cex-wallet-balance');
                    const cexUsdcEl = document.getElementById('cex-usdc');

                    if (cexBalEl) {
                        cexBalEl.textContent = '$' + (data.cex_wallet.total_value_usd || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    }
                    if (cexUsdcEl) {
                        cexUsdcEl.textContent = (data.cex_wallet.withdrawable_usdc || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    }
                }
                break;

            case 'SCALP_SIGNAL':
                // Real Engine Signal -> Dashboard Widget "Top Opportunity"
                this.updateScalpTarget(data);
                break;

            case 'SCALP_UPDATE':
                // Real Engine State -> Dashboard Widget Stats
                // Payload might be nested
                if (data.payload) this.updateScalpStats(data.payload);
                break;

                // Watchlist
                if (data.watchlist) {
                    // Update Dashboard Watchlist
                    if (this.activeComponents.sniper) {
                        this.activeComponents.sniper.update({ tokens: data.watchlist });
                    } else if (this.memeSniper) {
                        this.memeSniper.update({ tokens: data.watchlist });
                    }

                    // Update Scalp Engine Widget "Top Target"
                    // (Fallback: If no active signal, show top scanner result?)
                    // User requested "Fully Wired", so we prefer Engine Signals.
                    // Leaving this commented out or removed to avoid overriding real signals.
                    /*
                    if (data.watchlist && data.watchlist.length > 0) {
                        const topToken = data.watchlist.reduce((prev, current) =>
                            (prev.dp_24h || 0) > (current.dp_24h || 0) ? prev : current
                        );

                        const symbolEl = document.getElementById('scalp-target-symbol');
                        const spreadEl = document.getElementById('scalp-target-spread');

                        if (symbolEl && topToken) {
                            symbolEl.textContent = topToken.symbol;
                            // Using daily change or score as placeholder "spread" value logic if spread not available
                            const val = topToken.spread_pct || topToken.dp_24h || 0;
                            spreadEl.textContent = `+${val.toFixed(2)}%`;
                        }
                    }
                    */
                }


            case 'SIGNAL':
                // Handle generic signals (including Drift)
                this.handleSignal(data);
                break;

            case 'CONTEXT_UPDATE':
                this.headerStats.updateContext(data);
                break;

            case 'ENGINE_STATUS':
                this.updateEngineStates(data);
                break;

            case 'ENGINE_RESPONSE':
                this.handleEngineResponse(packet);
                // Safety Gate Toast Feedback
                if (!packet.result?.success) {
                    this.toast.show(packet.result?.message || 'Engine command failed', 'error');
                }
                break;

            case 'SOS_RESPONSE':
                this.handleSOSResponse(packet);
                break;

            case 'LOG_ENTRY':
                this.terminal.addLog(data.source, data.level, data.message, data.timestamp);
                break;

            case 'MARKET_DATA':
                this.marketData.update(data);
                if (data.sol_price) {
                    this.solTape.update(data.sol_price);
                    // Feed majors tape with available prices
                    this.majorsTape.update({
                        SOL: data.sol_price,
                        BTC: data.btc_price || 0,
                        ETH: data.eth_price || 0,
                        ...data.prices  // Additional prices if available
                    });
                }
                break;

            case 'TOKEN_WATCHLIST':
                if (this.tokenWatchlist) this.tokenWatchlist.update(data);
                if (this.memeSniper) this.memeSniper.update(data);
                break;

            case 'API_HEALTH':
                if (this.apiHealth) this.apiHealth.update(data);
                break;

            case 'ARB_OPP':
                this.updateIntelTable('ARB', data);
                if (this.marketComponents.arb) this.marketComponents.arb.update(data);
                break;

            case 'SCALP_SIGNAL':
                this.updateIntelTable('SCALP', data);
                if (this.marketComponents.scalp) this.marketComponents.scalp.update(data);
                break;

            case 'LST_UPDATE':
                if (this.marketComponents.lst) this.marketComponents.lst.update(data.data);
                break;

            case 'SCALP_UPDATE':
                if (this.marketComponents.scalp && data.payload?.type === 'SIGNAL') {
                    this.marketComponents.scalp.update(data.payload.data);
                }
                break;

            // ═══════════════════════════════════════════════════════════════
            // MULTI-VAULT MESSAGES
            // ═══════════════════════════════════════════════════════════════

            case 'ENGINE_VAULT':
                // Vault data response for detail view
                if (packet.engine && packet.data) {
                    this.updateVaultPanel(packet.engine, packet.data);
                }
                break;

            case 'VAULT_RESPONSE':
                // Vault reset/sync confirmation
                if (packet.success) {
                    this.toast.show(packet.message || 'Vault operation complete', 'success');
                    // Refresh vault data
                    if (packet.engine && this.currentDetailEngine === packet.engine) {
                        this.ws.send('GET_ENGINE_VAULT', { engine: packet.engine });
                    }
                } else {
                    this.toast.show(packet.message || 'Vault operation failed', 'error');
                }
                break;

            case 'VAULT_SNAPSHOT':
                // Global vault aggregation (for future portfolio view)
                console.log('Vault Snapshot:', packet.data);
                break;

            default:
                // Unhandled packet type
                break;
        }
    }

    /**
     * Update all engine states
     */
    updateEngineStates(states) {
        let runningCount = 0;

        Object.entries(states).forEach(([name, state]) => {
            if (this.engines[name]) {
                this.engines[name].setState(state);
                if (state.status === 'running') runningCount++;
            }
        });

        this.headerStats.setEngineCount(runningCount, Object.keys(this.engines).length);
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
     * Handle engine response
     */
    handleEngineResponse(packet) {
        const { engine, result } = packet;
        const level = result.success ? 'SUCCESS' : 'ERROR';
        this.terminal.addLog('ENGINE', level, `${engine}: ${result.message}`);
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
     * Switch between views
     */
    /**
     * Switch between views (Async Template Loading)
     */
    async switchView(viewName) {
        const viewId = `view-${viewName}`;
        let viewPanel = document.getElementById(viewId);

        // Nav State
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.view === viewName);
        });

        // Dynamic Loading
        if (!viewPanel) {
            // Show loading state?
            try {
                console.log(`Loading template: templates/${viewName}.html`);
                const response = await fetch(`templates/${viewName}.html`);

                if (response.ok) {
                    const html = await response.text();

                    // Create view container
                    viewPanel = document.createElement('div');
                    viewPanel.className = 'view-panel';
                    viewPanel.id = viewId;
                    viewPanel.innerHTML = html;

                    document.querySelector('.view-stack').appendChild(viewPanel);

                    // Initialize newly loaded components
                    this.initializeDynamicComponents(viewName);
                } else {
                    console.error(`Template ${viewName} not found`);
                    // Fallback to dashboard?
                }
            } catch (e) {
                console.error('View load error:', e);
            }
        }

        // Toggle Visibility
        document.querySelectorAll('.view-panel').forEach(panel => {
            panel.classList.toggle('active', panel.id === viewId);
        });

        // Request API health when entering Config view
        if (viewName === 'settings' && this.ws) {
            this.ws.send('GET_API_HEALTH', {});
        }
    }

    /**
     * Initialize components appearing in dynamic views
     */
    initializeDynamicComponents(viewName) {
        console.log(`Initializing components for ${viewName}`);
        if (this.layoutManager) this.layoutManager.refresh();

        if (viewName === 'dashboard') {
            try {
                // Initialize Dashboard Components
                this.unifiedVault = new UnifiedVaultController('unified-vault-container');
                // this.tokenWatchlist = new TokenWatchlist('watchlist-panel'); // Legacy - Replaced by MemeSniper
                this.inventory = new Inventory();
                this.systemMetrics = new SystemMetrics('chart-metrics');
                this.memeSniper = new MemeSniperStrip('meme-sniper-mount'); // Dashboard Instance

                // Active Scalp Engine Card (Dashboard Widget)
                this.scalpEngineWidget = new EngineCard('scalp', {
                    onToggle: (n, s, m) => this.toggleEngine(n, s, m),
                    onSettings: (n, c) => this.openSettings(n, c),
                    onModeChange: (n, m) => { if (this.engines[n]) this.engines[n].setMode(m); }
                });
                this.engines['scalp'] = this.scalpEngineWidget;
                if (this.unifiedVault) {
                    this.unifiedVault.setBridgeCallback((amount) => {
                        this.ws.send('BRIDGE_TRIGGER', { amount });
                        this.terminal.addLog('BRIDGE', 'INFO', `Bridge initiated: $${amount.toFixed(2)} USDC -> Phantom`);
                    });
                }

                // Request Initial Data
                if (this.ws && this.ws.connected) {
                    this.ws.send('GET_SYSTEM_STATS', {});
                    this.ws.send('GET_WATCHLIST', {});
                }
            } catch (e) {
                console.error("Error initializing dashboard components:", e);
            }
        }

        if (viewName.startsWith('engine-')) {
            const engineId = viewName.replace('engine-', '');
            // Engine specific init logic can go here
        }

        if (viewName === 'settings') {
            try {
                this.apiHealth = new APIHealth('api-health-container');
                // Request initial health data
                if (this.ws && this.ws.connected) this.ws.send('GET_API_HEALTH', {});
            } catch (e) {
                console.error("Error initializing settings components:", e);
            }
        }

        if (viewName === 'scanner') {
            try {
                this.marketComponents['arb'] = new ArbScanner('arb', '#arb-scanner-mount');
                this.marketComponents['funding'] = new FundingMonitor('funding', '#funding-scanner-mount');
            } catch (e) {
                console.error("Error initializing scanner components:", e);
            }
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
