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
import { TickerTape } from './components/ticker-tape.js';
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

}

// Initialize when DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.tradingOS = new TradingOS();
});
