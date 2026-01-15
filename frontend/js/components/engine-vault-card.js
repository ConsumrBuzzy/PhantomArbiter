/**
 * EngineVaultCard (Web Component)
 * ===============================
 * Displays the "Dedicated Vault" for a specific engine.
 * Shows: Allocation, Available Capital, PnL, and Transfer Actions.
 */

export class EngineVaultCard {
    constructor(containerId, engineName, config = {}) {
        this.container = document.getElementById(containerId);
        this.engineName = engineName.toUpperCase();
        this.config = {
            color: config.color || '#875BF7', // Default Purple
            icon: config.icon || 'fa-box',
            ...config
        };

        this.state = {
            allocated: 0,
            available: 0,
            pnl_realized: 0,
            pnl_unrealized: 0
        };

        this.render();
    }

    update(data) {
        if (!data) return;
        this.state = { ...this.state, ...data };
        this._refreshDOM();
    }

    render() {
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="drift-vault-card" style="border-top-color: ${this.config.color};">
                <!-- Header -->
                <div class="drift-header">
                    <div class="drift-logo" style="color: ${this.config.color}; text-shadow: 0 0 10px ${this.config.color}40;">
                        <i class="fa-solid ${this.config.icon}"></i>
                        <span>${this.engineName} VAULT</span>
                    </div>
                    <span class="drift-status-badge">ACTIVE</span>
                </div>

                <!-- Stats Grid -->
                <div class="drift-stats-grid">
                    <div class="drift-stat">
                        <span class="drift-label">Allocated</span>
                        <span class="drift-value" id="ev-allocated">$0.00</span>
                    </div>
                    <div class="drift-stat">
                        <span class="drift-label">Available</span>
                        <span class="drift-value" id="ev-available">$0.00</span>
                    </div>
                    <div class="drift-stat">
                        <span class="drift-label">PnL (u)</span>
                        <span class="drift-value" id="ev-pnl">$0.00</span>
                    </div>
                </div>

                <!-- Actions -->
                <div class="drift-actions">
                    <button class="drift-btn" onclick="window.triggerVaultAction('${this.engineName}', 'deposit')">
                        <i class="fa-solid fa-arrow-down"></i> Deposit
                    </button>
                    <button class="drift-btn" onclick="window.triggerVaultAction('${this.engineName}', 'withdraw')">
                        <i class="fa-solid fa-arrow-up"></i> Withdraw
                    </button>
                </div>
            </div>
        `;
    }

    _refreshDOM() {
        this._setText('ev-allocated', this._formatUSD(this.state.allocated));
        this._setText('ev-available', this._formatUSD(this.state.available));

        // PnL with coloring
        const pnlEl = this.container.querySelector('#ev-pnl');
        if (pnlEl) {
            pnlEl.textContent = (this.state.pnl_unrealized >= 0 ? '+' : '') + this._formatUSD(this.state.pnl_unrealized);
            pnlEl.className = `drift-value ${this.state.pnl_unrealized >= 0 ? 'positive' : 'negative'}`;
        }
    }

    _formatUSD(val) {
        return '$' + (val || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    _setText(id, text) {
        // Scoped query within container to support multiple cards
        const el = this.container.querySelector(`#${id}`);
        if (el) el.textContent = text;
    }
}
