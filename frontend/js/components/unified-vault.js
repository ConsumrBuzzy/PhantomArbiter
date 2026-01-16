/**
 * UnifiedVaultController - The "CFO" Component
 * =============================================
 * Aggregates all wallet data into a single source of truth.
 * 
 * Pillars:
 * - Coinbase (CEX): USDC, USD, SOL holdings
 * - Phantom (DEX): SOL, tokens, on-chain balance
 * - Drift (Perp): Equity, PnL, Leverage
 * 
 * Features:
 * - Net Worth calculation across all venues
 * - Bridge Control (Coinbase → Phantom)
 * - Engine-specific allocation views
 */

export class UnifiedVaultController {
    constructor(containerId) {
        console.log(`[UnifiedVault] Initializing with container ID: ${containerId}`);
        this.container = document.getElementById(containerId);
        console.log(`[UnifiedVault] Container found:`, this.container);

        this.data = {
            coinbase: { usdc: 0, usd: 0, sol: 0, total: 0, status: 'disconnected' },
            phantom: { sol: 0, usdc: 0, total: 0, status: 'disconnected' },
            drift: { equity: 0, pnl: 0, leverage: 0, status: 'disconnected' },
            net_worth: 0,
            deployed: 0,
            idle: 0,
            bridge: { available: false, max_amount: 0 }
        };

        this.onBridgeClick = null; // Callback for bridge action
        this.render();
    }

    /**
     * Render the 3-pillar vault view
     */
    render() {
        if (!this.container) {
            console.error('[UnifiedVault] Render failed: Container is missing!');
            return;
        }
        console.log('[UnifiedVault] Rendering to container...');

        this.container.innerHTML = `
            <div class="unified-vault">
                <div class="vault-header">
                    <span class="vault-title">💎 UNIVERSAL VAULT</span>
                    <span class="vault-net-worth" id="vault-net-worth">$0.00</span>
                </div>
                
                <div class="vault-pillars">
                    <!-- Coinbase Pillar -->
                    <div class="vault-pillar" id="pillar-coinbase">
                        <div class="pillar-header">
                            <span class="pillar-icon" style="background: #0052FF;">₿</span>
                            <span class="pillar-name">COINBASE</span>
                            <span class="pillar-status" id="status-coinbase">●</span>
                        </div>
                        <div class="pillar-balance">
                            <div class="balance-row">
                                <span class="balance-label">USDC</span>
                                <span class="balance-value" id="cb-usdc">$0.00</span>
                            </div>
                            <div class="balance-row">
                                <span class="balance-label">USD</span>
                                <span class="balance-value" id="cb-usd">$0.00</span>
                            </div>
                            <div class="balance-row">
                                <span class="balance-label">SOL</span>
                                <span class="balance-value" id="cb-sol">0.00</span>
                            </div>
                        </div>
                        <div class="pillar-total">
                            <span id="cb-total">$0.00</span>
                        </div>
                    </div>

                    <!-- Phantom Pillar -->
                    <div class="vault-pillar" id="pillar-phantom">
                        <div class="pillar-header">
                            <span class="pillar-icon" style="background: linear-gradient(135deg, #AB9FF2, #6366F1);">👻</span>
                            <span class="pillar-name">PHANTOM</span>
                            <span class="pillar-status" id="status-phantom">●</span>
                        </div>
                        <div class="pillar-balance">
                            <div class="balance-row">
                                <span class="balance-label">SOL</span>
                                <span class="balance-value" id="ph-sol">0.00</span>
                            </div>
                            <div class="balance-row">
                                <span class="balance-label">USDC</span>
                                <span class="balance-value" id="ph-usdc">$0.00</span>
                            </div>
                            <div class="balance-row">
                                <span class="balance-label">Tokens</span>
                                <span class="balance-value" id="ph-tokens">--</span>
                            </div>
                        </div>
                        <div class="pillar-total">
                            <span id="ph-total">$0.00</span>
                        </div>
                    </div>

                    <!-- Drift Pillar -->
                    <div class="vault-pillar" id="pillar-drift">
                        <div class="pillar-header">
                            <span class="pillar-icon" style="background: linear-gradient(135deg, #00D4FF, #7C3AED);">🌊</span>
                            <span class="pillar-name">DRIFT</span>
                            <span class="pillar-status" id="status-drift">●</span>
                        </div>
                        <div class="pillar-balance">
                            <div class="balance-row">
                                <span class="balance-label">Equity</span>
                                <span class="balance-value" id="dr-equity">$0.00</span>
                            </div>
                            <div class="balance-row">
                                <span class="balance-label">PnL</span>
                                <span class="balance-value" id="dr-pnl">$0.00</span>
                            </div>
                            <div class="balance-row">
                                <span class="balance-label">Leverage</span>
                                <span class="balance-value" id="dr-leverage">0x</span>
                            </div>
                        </div>
                        <div class="pillar-total">
                            <span id="dr-total">$0.00</span>
                        </div>
                    </div>
                </div>

                <div class="vault-footer">
                    <div class="vault-allocation">
                        <div class="alloc-item">
                            <span class="alloc-label">Deployed</span>
                            <span class="alloc-value" id="vault-deployed">$0.00</span>
                        </div>
                        <div class="alloc-item">
                            <span class="alloc-label">Idle</span>
                            <span class="alloc-value" id="vault-idle">$0.00</span>
                        </div>
                    </div>
                    <button class="vault-bridge-btn" id="bridge-btn" disabled>
                        🌉 BRIDGE USDC →
                    </button>
                </div>
            </div>
        `;

        // Bind bridge button
        const bridgeBtn = document.getElementById('bridge-btn');
        if (bridgeBtn) {
            bridgeBtn.addEventListener('click', () => {
                if (this.onBridgeClick && this.data.bridge.available) {
                    this.onBridgeClick(this.data.bridge.max_amount);
                }
            });
        }
    }

    /**
     * Update vault with unified balance data
     * @param {Object} unifiedBalance - The unified_balance object from backend
     */
    update(unifiedBalance) {
        if (!unifiedBalance) return;

        // Store data
        this.data = {
            coinbase: unifiedBalance.coinbase || this.data.coinbase,
            phantom: unifiedBalance.phantom || this.data.phantom,
            drift: unifiedBalance.drift || this.data.drift,
            net_worth: unifiedBalance.net_worth_usd || 0,
            deployed: unifiedBalance.deployed_usd || 0,
            idle: unifiedBalance.idle_usd || 0,
            bridge: unifiedBalance.bridge || { available: false, max_amount: 0 }
        };

        this._updateDOM();
    }

    /**
     * Update DOM elements with current data
     */
    _updateDOM() {
        const { coinbase, phantom, drift, net_worth, deployed, idle, bridge } = this.data;

        // Net Worth
        this._setText('vault-net-worth', this._formatUSD(net_worth));

        // Coinbase
        this._setText('cb-usdc', this._formatUSD(coinbase.usdc || 0));
        this._setText('cb-usd', this._formatUSD(coinbase.usd || 0));
        this._setText('cb-sol', (coinbase.sol || 0).toFixed(4));
        this._setText('cb-total', this._formatUSD(coinbase.total || 0));
        this._setStatus('status-coinbase', coinbase.status);

        // Phantom
        this._setText('ph-sol', (phantom.sol || 0).toFixed(4));
        this._setText('ph-usdc', this._formatUSD(phantom.usdc || 0));
        this._setText('ph-tokens', phantom.token_count || '--');
        this._setText('ph-total', this._formatUSD(phantom.total || 0));
        this._setStatus('status-phantom', phantom.status);

        // Drift
        this._setText('dr-equity', this._formatUSD(drift.equity || 0));
        this._setText('dr-pnl', this._formatPnL(drift.pnl || 0));
        this._setText('dr-leverage', (drift.leverage || 0).toFixed(1) + 'x');
        this._setText('dr-total', this._formatUSD(drift.equity || 0));
        this._setStatus('status-drift', drift.status);

        // Allocation
        this._setText('vault-deployed', this._formatUSD(deployed));
        this._setText('vault-idle', this._formatUSD(idle));

        // Bridge Button
        const bridgeBtn = document.getElementById('bridge-btn');
        if (bridgeBtn) {
            bridgeBtn.disabled = !bridge.available;
            if (bridge.available && bridge.max_amount > 0) {
                bridgeBtn.textContent = `🌉 BRIDGE $${bridge.max_amount.toFixed(0)} →`;
                bridgeBtn.classList.add('available');
            } else {
                bridgeBtn.textContent = '🌉 BRIDGE USDC →';
                bridgeBtn.classList.remove('available');
            }
        }
    }

    _setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    _setStatus(id, status) {
        const el = document.getElementById(id);
        if (!el) return;

        el.className = 'pillar-status';
        if (status === 'connected') {
            el.classList.add('connected');
            el.title = 'Connected';
        } else if (status === 'error') {
            el.classList.add('error');
            el.title = 'Error - Click to reconnect';
        } else {
            el.classList.add('disconnected');
            el.title = 'Disconnected';
        }
    }

    _formatUSD(value) {
        return '$' + (value || 0).toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    _formatPnL(value) {
        const formatted = this._formatUSD(Math.abs(value));
        if (value >= 0) {
            return '+' + formatted;
        }
        return '-' + formatted;
    }

    /**
     * Set bridge click callback
     * @param {Function} callback - fn(maxAmount)
     */
    setBridgeCallback(callback) {
        this.onBridgeClick = callback;
    }

    /**
     * Trigger reconnect attempt for a specific venue
     * @param {string} venue - coinbase, phantom, or drift
     */
    reconnect(venue) {
        console.log(`[UnifiedVault] Reconnecting ${venue}...`);
        // This would emit a WebSocket message to trigger reconnection
    }
}
