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
import { WhaleTape } from './components/whale-tape.js';
import { ModalManager } from './components/modal.js';
import { HeaderStats } from './components/header-stats.js';

class TradingOS {
    constructor() {
        // Initialize components
        this.terminal = new Terminal('log-stream');
        this.marketData = new MarketData();
        this.marketData = new MarketData();
        this.tokenWatchlist = new TokenWatchlist('watchlist-panel');
        this.inventory = new Inventory('inventory-table');
        this.headerStats = new HeaderStats();
        this.whaleTape = new WhaleTape('whale-tape-content');
        this.modal = new ModalManager();

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

            // Update all engine cards to match default if not manually overridden
            Object.values(this.engines).forEach(card => card.setMode(mode.toLowerCase()));
        };

        // Bind navigation and SOS
        this.bindGlobalEvents();

        // Connect
        const url = this.ws.connect();
        this.terminal.addLog('SYSTEM', 'INFO', `Connecting to Command Center: ${url}...`);
    }

    /**
     * Bind global UI events (navigation, SOS)
     */
    bindGlobalEvents() {
        // Navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => this.switchView(item.dataset.view));
        });

        // SOS Button
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
                if (data.wallet) this.inventory.update(data.wallet);
                if (data.engines) this.updateEngineStates(data.engines);
                break;

            case 'CONTEXT_UPDATE':
                this.headerStats.updateContext(data);
                break;

            case 'ENGINE_STATUS':
                this.updateEngineStates(data);
                break;

            case 'ENGINE_RESPONSE':
                this.handleEngineResponse(packet);
                break;

            case 'SOS_RESPONSE':
                this.handleSOSResponse(packet);
                break;

            case 'LOG_ENTRY':
                this.terminal.addLog(data.source, data.level, data.message, data.timestamp);
                break;

            case 'MARKET_DATA':
                this.marketData.update(data);
                break;

            case 'TOKEN_WATCHLIST':
                this.tokenWatchlist.update(data);
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
    switchView(viewName) {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.view === viewName);
        });

        document.querySelectorAll('.view-panel').forEach(panel => {
            panel.classList.toggle('active', panel.id === `view-${viewName}`);
        });
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
