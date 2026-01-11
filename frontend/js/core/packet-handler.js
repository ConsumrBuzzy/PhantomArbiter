import { createWhaleItem } from '../components/ticker-tape.js';

/**
 * Packet Handler
 * ==============
 * Decouples WebSocket message routing from the main Application Controller.
 */
export class PacketHandler {
    constructor(app) {
        this.app = app;
    }

    handle(packet) {
        const { type, data } = packet;
        const app = this.app;

        switch (type) {
            case 'SYSTEM_STATS':
                app.headerStats.update(data);
                if (data.live_wallet || data.paper_wallet) app.inventory.update(data);
                if (data.engines) this.updateEngineStates(data.engines);
                if (data.metrics) app.systemMetrics.update(data.metrics);

                // Watchlist
                if (data.watchlist) {
                    if (app.activeComponents.sniper) {
                        app.activeComponents.sniper.update({ tokens: data.watchlist });
                    } else if (app.memeSniper) {
                        app.memeSniper.update({ tokens: data.watchlist });
                    }
                }

                // UNIFIED BALANCE
                if (data.unified_balance) {
                    // Update UnifiedVault (Global or Page-Specific)
                    if (app.activeComponents.vault) {
                        app.activeComponents.vault.update(data.unified_balance);
                    } else if (app.unifiedVault) {
                        app.unifiedVault.update(data.unified_balance);
                    }

                    // Update Drift Panel (legacy DOM manipulation for now, pending full Drift Page)
                    const driftEquity = data.unified_balance.drift?.equity || 0;
                    const equityEl = document.getElementById('drift-equity');
                    const pnlEl = document.getElementById('drift-pnl');

                    if (equityEl) equityEl.textContent = '$' + driftEquity.toFixed(2);
                    if (driftEquity > 0 && pnlEl) {
                        const pnl = data.unified_balance.drift?.pnl || 0;
                        pnlEl.textContent = (pnl >= 0 ? '+' : '') + '$' + Math.abs(pnl).toFixed(2);
                        pnlEl.className = 'drift-value ' + (pnl >= 0 ? 'positive' : 'negative');
                    }

                    // Update ticker mode
                    if (data.mode && app.whaleTicker) {
                        app.whaleTicker.setMode(data.mode);
                    }
                }

                // LEGACY CEX UPDATE
                if (data.cex_wallet && !data.unified_balance) {
                    const cexBalEl = document.getElementById('cex-wallet-balance');
                    const cexUsdcEl = document.getElementById('cex-usdc');
                    if (cexBalEl) cexBalEl.textContent = '$' + (data.cex_wallet.total_value_usd || 0).toLocaleString('en-US', { minimumFractionDigits: 2 });
                    if (cexUsdcEl) cexUsdcEl.textContent = (data.cex_wallet.withdrawable_usdc || 0).toLocaleString('en-US', { minimumFractionDigits: 2 });
                }
                break;

            case 'SIGNAL':
                this.handleSignal(data);
                break;

            case 'CONTEXT_UPDATE':
                app.headerStats.updateContext(data);
                break;

            case 'ENGINE_STATUS':
                this.updateEngineStates(data);
                break;

            case 'ENGINE_RESPONSE':
                this.handleEngineResponse(packet);
                if (!packet.result?.success) {
                    app.toast.show(packet.result?.message || 'Engine command failed', 'error');
                }
                break;

            case 'SOS_RESPONSE':
                this.handleSOSResponse(packet);
                break;

            case 'LOG_ENTRY':
                app.terminal.addLog(data.source, data.level, data.message, data.timestamp);
                break;

            case 'MARKET_DATA':
                app.marketData.update(data);
                if (data.sol_price) {
                    app.solTape.update(data.sol_price);
                    app.majorsTape.update({
                        SOL: data.sol_price,
                        BTC: data.btc_price || 0,
                        ETH: data.eth_price || 0,
                        ...data.prices
                    });
                }
                break;

            case 'TOKEN_WATCHLIST':
                app.tokenWatchlist.update(data);
                if (app.activeComponents.sniper) {
                    app.activeComponents.sniper.update({ tokens: data });
                } else {
                    app.memeSniper.update({ tokens: data });
                }
                break;

            case 'API_HEALTH':
                if (app.apiHealth) app.apiHealth.update(data);
                break;

            case 'ARB_OPP':
                // app.updateIntelTable('ARB', data); // Legacy logic, possibly undefined?
                if (app.marketComponents.arb) app.marketComponents.arb.update(data);
                break;

            case 'SCALP_SIGNAL':
                if (app.marketComponents.scalp) app.marketComponents.scalp.update(data);
                break;

            case 'LST_UPDATE':
                if (app.marketComponents.lst) app.marketComponents.lst.update(data.data);
                break;

            case 'SCALP_UPDATE':
                if (app.marketComponents.scalp && data.payload?.type === 'SIGNAL') {
                    app.marketComponents.scalp.update(data.payload.data);
                }
                break;

            case 'ENGINE_VAULT':
                if (packet.engine && packet.data) {
                    this.updateVaultPanel(packet.engine, packet.data);
                }
                break;

            case 'VAULT_RESPONSE':
                if (packet.success) {
                    app.toast.show(packet.message || 'Vault operation complete', 'success');
                    if (packet.engine && app.currentDetailEngine === packet.engine) {
                        app.ws.send('GET_ENGINE_VAULT', { engine: packet.engine });
                    }
                } else {
                    app.toast.show(packet.message || 'Vault operation failed', 'error');
                }
                break;

            case 'VAULT_SNAPSHOT':
                console.log('Vault Snapshot:', packet.data);
                break;
        }
    }

    updateEngineStates(states) {
        let runningCount = 0;
        Object.entries(states).forEach(([name, state]) => {
            if (this.app.engines[name]) {
                this.app.engines[name].setState(state);
                if (state.status === 'running') runningCount++;
            }
        });
        this.app.headerStats.setEngineCount(runningCount, Object.keys(this.app.engines).length);
    }

    handleSignal(payload) {
        // Drift Ticker Update
        const ticker = document.getElementById('drift-ticker');
        if (ticker && payload) {
            let msg = '';
            if (payload.type === 'funding') {
                msg = `💰 Funding Opp: ${payload.symbol} ${payload.apr}% APR`;
            } else if (payload.type === 'arb') msg = `⚡ Arb Signal: ${payload.symbol} -> ${payload.profit_pct}%`;

            if (msg) {
                ticker.textContent = msg;
                ticker.style.animation = 'none';
                ticker.offsetHeight;
                ticker.style.animation = 'pulse-text 2s infinite';
            }
        }

        // Whale Tape
        if (payload.type === 'WHALE_ACTIVITY' || payload.source === 'WHALE') {
            const data = payload.data || {};
            const symbol = data.mint || data.symbol || 'UNK';
            const value = data.amount_usd || data.value || 50000;
            const direction = (data.direction || 'buy').toLowerCase();

            const item = createWhaleItem(symbol, value, direction);
            if (this.app.whaleTicker) {
                this.app.whaleTicker.addItem(item);
            }
        }
    }

    handleEngineResponse(packet) {
        const { engine, result } = packet;
        const level = result.success ? 'SUCCESS' : 'ERROR';
        this.app.terminal.addLog('ENGINE', level, `${engine}: ${result.message}`);
    }

    handleSOSResponse(packet) {
        const { result } = packet;
        if (result.success) {
            this.app.terminal.addLog('SYSTEM', 'WARNING', `SOS Complete: ${result.engines_stopped} engines stopped`);
        } else {
            this.app.terminal.addLog('SYSTEM', 'ERROR', `SOS Failed: ${result.message}`);
        }
    }

    updateVaultPanel(engineId, vaultData) {
        if (this.app.currentDetailEngine !== engineId) return;

        const equityEl = document.getElementById('detail-vault-equity');
        if (equityEl) equityEl.textContent = `$${(vaultData.equity || 0).toFixed(2)}`;

        const assetsContainer = document.getElementById('detail-vault-assets');
        if (assetsContainer && vaultData.assets) {
            let html = '';
            Object.entries(vaultData.assets).sort((a, b) => {
                if (a[0] === 'USDC') return -1;
                if (b[0] === 'USDC') return 1;
                return 0;
            }).forEach(([asset, balance]) => {
                const displayBal = balance >= 1 ? balance.toFixed(2) : balance.toFixed(4);
                html += `<div class="vault-asset-row"><span class="vault-asset-symbol">${asset}</span><span class="vault-asset-balance">${displayBal}</span></div>`;
            });
            assetsContainer.innerHTML = html || '<div class="vault-asset-row"><span>No assets</span></div>';
        }
    }
}
