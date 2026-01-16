/**
 * Packet Handler - WebSocket Message Router
 * =========================================
 * Decouples message processing from the main application class.
 * Routes incoming data to appropriate managers and components.
 */
export class PacketHandler {
    constructor(app) {
        this.app = app;
    }

    /**
     * Dispatch incoming packet to specific handlers
     * @param {Object} packet - { type, data, ... }
     */
    handle(packet) {
        const { type, data } = packet;

        switch (type) {
            case 'SYSTEM_STATS':
                this.handleSystemStats(data);
                break;

            case 'SCALP_SIGNAL':
                this.app.updateScalpTarget(data);
                break;

            case 'SCALP_UPDATE':
                if (data.payload) this.app.updateScalpStats(data.payload);
                break;

            case 'SIGNAL':
                this.app.handleSignal(data);
                break;

            case 'CONTEXT_UPDATE':
                this.app.headerStats.updateContext(data);
                break;

            case 'ENGINE_STATUS':
                this.app.engineManager.updateStates(data);
                break;

            case 'ENGINE_RESPONSE':
                this.app.engineManager.handleResponse(packet);
                if (!packet.result?.success) {
                    this.app.toast.show(packet.result?.message || 'Engine command failed', 'error');
                }
                break;

            case 'SOS_RESPONSE':
                this.app.handleSOSResponse(packet);
                break;

            case 'LOG_ENTRY':
                this.app.terminal.addLog(data.source, data.level, data.message, data.timestamp);
                break;

            case 'MARKET_DATA':
                this.handleMarketData(data);
                break;

            case 'TOKEN_WATCHLIST':
                if (this.app.tokenWatchlist) this.app.tokenWatchlist.update(data);
                if (this.app.memeSniper) this.app.memeSniper.update(data);
                break;

            case 'API_HEALTH':
                if (this.app.apiHealth) this.app.apiHealth.update(data);
                break;

            case 'ARB_OPP':
                this.app.updateIntelTable('ARB', data);
                if (this.app.marketComponents.arb) this.app.marketComponents.arb.update(data);
                break;

            case 'LST_UPDATE':
                if (this.app.marketComponents.lst) this.app.marketComponents.lst.update(data.data);
                break;

            // Multi-Vault Messages
            case 'ENGINE_VAULT':
                if (packet.engine && packet.data) {
                    this.app.engineManager.updateVaultPanel(packet.engine, packet.data);
                }
                break;

            case 'VAULT_RESPONSE':
                if (packet.success) {
                    this.app.toast.show(packet.message || 'Vault operation complete', 'success');
                    if (packet.engine && this.app.currentDetailEngine === packet.engine) {
                        this.app.ws.send('GET_ENGINE_VAULT', { engine: packet.engine });
                    }
                } else {
                    this.app.toast.show(packet.message || 'Vault operation failed', 'error');
                }
                break;

            case 'VAULT_SNAPSHOT':
                console.log('Vault Snapshot:', packet.data);
                break;

            default:
                // console.warn('Unhandled packet:', type);
                break;
        }
    }

    /**
     * Handle System Stats (Heartbeat)
     */
    handleSystemStats(data) {
        // Headers & Inventory
        this.app.headerStats.update(data);
        if ((data.live_wallet || data.paper_wallet) && this.app.inventory) {
            this.app.inventory.update(data);
        }

        // Engines & Metrics
        if (data.engines) this.app.engineManager.updateStates(data.engines);
        if (data.metrics && this.app.systemMetrics) this.app.systemMetrics.update(data.metrics);

        // Unified Balance (Single Source of Truth)
        if (data.unified_balance) {
            // Update VaultController
            if (this.app.activeComponents.vault) {
                this.app.activeComponents.vault.update(data.unified_balance);
            } else if (this.app.unifiedVault) {
                this.app.unifiedVault.update(data.unified_balance);
            }

            // Update Drift Panel Elements (Legacy)
            const driftEquity = data.unified_balance.drift?.equity || 0;
            const equityEl = document.getElementById('drift-equity');
            const pnlEl = document.getElementById('drift-pnl');

            if (equityEl) equityEl.textContent = '$' + driftEquity.toFixed(2);
            if (driftEquity > 0 && pnlEl) {
                const pnl = data.unified_balance.drift?.pnl || 0;
                pnlEl.textContent = (pnl >= 0 ? '+' : '') + '$' + Math.abs(pnl).toFixed(2);
                pnlEl.className = 'drift-value ' + (pnl >= 0 ? 'positive' : 'negative');
            }

            // Sync Global Mode
            if (data.mode && this.app.whaleTicker) {
                this.app.whaleTicker.setMode(data.mode);
            }
        }

        // Watchlist
        if (data.watchlist) {
            if (this.app.activeComponents.sniper) {
                this.app.activeComponents.sniper.update({ tokens: data.watchlist });
            } else if (this.app.memeSniper) {
                this.app.memeSniper.update({ tokens: data.watchlist });
            }
        }

        // Legacy CEX UI (Backward Compatibility)
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
    }

    /**
     * Handle Market Data Update
     */
    handleMarketData(data) {
        this.app.marketData.update(data);
        if (data.sol_price) {
            this.app.solTape.update(data.sol_price);
            this.app.majorsTape.update({
                SOL: data.sol_price,
                BTC: data.btc_price || 0,
                ETH: data.eth_price || 0,
                ...data.prices
            });
        }
    }
}
