/**
 * EngineRow Component
 * ====================
 * Glanceable engine status card for the Opportunity Matrix.
 * 
 * Consumes data from the UIProtocol (RenderPayload.engines).
 */

export class EngineRow {

    /**
     * Create an EngineRow component.
     * @param {string} containerId - DOM container ID
     * @param {function} onDetailClick - Callback when card is clicked
     */
    constructor(containerId, onDetailClick = null) {
        this.container = document.getElementById(containerId);
        this.onDetailClick = onDetailClick;
        this.engines = new Map();
    }

    /**
     * Update engine displays from RenderPayload.
     * @param {Array} engines - Array of EngineUIState objects
     */
    update(engines) {
        if (!this.container) return;

        // Update or create cards
        engines.forEach(engine => {
            let card = this.engines.get(engine.engine_id);

            if (!card) {
                card = this._createCard(engine);
                this.engines.set(engine.engine_id, card);
                this.container.appendChild(card);
            }

            this._updateCard(card, engine);
        });
    }

    /**
     * Create a new engine card.
     */
    _createCard(engine) {
        const card = document.createElement('div');
        card.className = 'engine-row';
        card.id = `engine-${engine.engine_id}`;

        card.innerHTML = `
            <div class="engine-header">
                <div class="engine-name">
                    <span class="engine-status-icon"></span>
                    <span class="engine-name-text">${engine.display_name}</span>
                </div>
                <span class="engine-mode-badge paper">${engine.mode}</span>
            </div>
            <div class="engine-metric-primary">
                <span class="metric-value">--</span>
                <span class="metric-unit">${engine.primary_metric_unit}</span>
            </div>
            <div class="metric-label">${engine.primary_metric_label}</div>
            <div class="engine-status-text">Idle</div>
            <div class="engine-pnl">
                <span class="pnl-value neutral">$0.00</span>
                <span class="trade-count">0 trades</span>
            </div>
        `;

        // Click handler for detail view
        card.addEventListener('click', () => {
            if (this.onDetailClick) {
                this.onDetailClick(engine.engine_id);
            }
        });

        return card;
    }

    /**
     * Update an existing card.
     */
    _updateCard(card, engine) {
        // Update data attributes
        card.dataset.mode = engine.mode;
        card.dataset.running = engine.is_running;
        card.dataset.urgency = engine.urgency;

        // Update mode badge
        const badge = card.querySelector('.engine-mode-badge');
        badge.textContent = engine.mode;
        badge.className = `engine-mode-badge ${engine.mode.toLowerCase()}`;

        // Update primary metric
        const metricValue = card.querySelector('.metric-value');
        metricValue.textContent = this._formatMetric(engine.primary_metric, engine.primary_metric_unit);

        // Update status text
        const statusText = card.querySelector('.engine-status-text');
        statusText.textContent = engine.status_text;

        // Update PnL
        const pnlValue = card.querySelector('.pnl-value');
        const pnl = engine.pnl_session;
        pnlValue.textContent = `${pnl >= 0 ? '+' : ''}$${Math.abs(pnl).toFixed(2)}`;
        pnlValue.className = `pnl-value ${pnl > 0 ? 'positive' : pnl < 0 ? 'negative' : 'neutral'}`;

        // Update trade count
        const tradeCount = card.querySelector('.trade-count');
        tradeCount.textContent = `${engine.trades_count} trades`;
    }

    /**
     * Format metric value based on unit.
     */
    _formatMetric(value, unit) {
        if (unit === '%') {
            return value.toFixed(2);
        } else if (unit === '$') {
            return value.toFixed(2);
        }
        return value.toString();
    }

    /**
     * Clear all engine cards.
     */
    clear() {
        if (this.container) {
            this.container.innerHTML = '';
        }
        this.engines.clear();
    }
}


/**
 * OpportunityMatrix Component
 * ===========================
 * Heat-map display of active opportunities.
 */
export class OpportunityMatrix {

    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.opportunities = [];
    }

    /**
     * Update opportunities from RenderPayload.
     * @param {Array} opportunities - Array of OpportunitySnapshot objects
     */
    update(opportunities) {
        if (!this.container) return;

        this.opportunities = opportunities;
        this._render();
    }

    _render() {
        if (this.opportunities.length === 0) {
            this.container.innerHTML = `
                <div class="no-opportunities">
                    <span>📊</span>
                    <span>Scanning for opportunities...</span>
                </div>
            `;
            return;
        }

        const html = this.opportunities.map(opp => `
            <div class="opportunity-item" data-urgency="${opp.risk_level}">
                <div class="opp-info">
                    <span class="opp-pair">${opp.asset_pair}</span>
                    <span class="opp-type">${opp.opportunity_type}
                        ${opp.time_sensitivity !== 'LOW' ?
                `<span class="time-badge ${opp.time_sensitivity.toLowerCase()}">${opp.time_sensitivity}</span>`
                : ''}
                    </span>
                </div>
                <div class="opp-metrics">
                    <span class="opp-profit">+$${opp.profit_estimate_usd.toFixed(2)}</span>
                    <span class="opp-pct">${(opp.profit_estimate_pct * 100).toFixed(2)}%</span>
                </div>
            </div>
        `).join('');

        this.container.innerHTML = html;
    }
}


/**
 * DashboardHeader Component
 * =========================
 * Global header with equity, delta status, and mode indicator.
 */
export class DashboardHeader {

    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this._createStructure();
    }

    _createStructure() {
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="header-left">
                <div class="system-title">PHANTOM ARBITER</div>
                <div class="sol-price" id="header-sol-price">$--</div>
            </div>
            <div class="header-right">
                <div class="delta-status" id="header-delta">
                    <span class="delta-label">DELTA</span>
                    <span class="delta-value" id="delta-value">0.0%</span>
                </div>
                <div class="equity-display">
                    <div class="equity-label">EQUITY</div>
                    <div class="equity-value" id="header-equity">$--</div>
                </div>
            </div>
        `;
    }

    /**
     * Update header from RenderPayload.
     */
    update(payload) {
        // SOL price
        const solPrice = document.getElementById('header-sol-price');
        if (solPrice) {
            solPrice.textContent = `$${payload.sol_price.toFixed(2)}`;
        }

        // Equity (use active mode's equity)
        const equity = document.getElementById('header-equity');
        if (equity) {
            const value = payload.global_mode === 'PAPER'
                ? payload.paper_equity_usd
                : payload.live_equity_usd;
            equity.textContent = `$${value.toFixed(2)}`;
        }

        // Delta status
        const deltaContainer = document.getElementById('header-delta');
        const deltaValue = document.getElementById('delta-value');
        if (deltaContainer && deltaValue) {
            deltaValue.textContent = `${payload.delta_drift_pct.toFixed(2)}%`;

            // Update status class
            deltaContainer.classList.remove('warning', 'critical');
            if (payload.delta_drift_pct > 5.0) {
                deltaContainer.classList.add('critical');
            } else if (payload.delta_drift_pct > 2.0) {
                deltaContainer.classList.add('warning');
            }
        }
    }
}
