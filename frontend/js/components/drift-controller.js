/**
 * DriftController
 * ===============
 * "Risk-First" Controller for the Drift Engine.
 * 
 * Responsibilities:
 * 1. Health Monitor: Drives the SVG Gauge based on maintenance margin.
 * 2. Split-Brain Immunity: Prioritizes Streamed Account Data over Polled.
 * 3. Position Management: Renders the "Combat Zone" table.
 */

export class DriftController {
    constructor() {
        this.initialized = false;
        this.activeSubAccount = 0;

        // State
        this.state = {
            health: 100,
            leverage: 0,
            maintenance_margin: 0,
            initial_margin: 0,
            total_collateral: 0,
            free_collateral: 0,
            unrealized_pnl: 0,
            positions: []
        };

        // DOM Elements
        this.els = {
            gauge: {
                needle: null,
                value: null,
                container: null
            },
            metrics: {
                total: null,
                free: null,
                maint: null
            },
            leverage: {
                fill: null,
                value: null
            },
            delta: {
                val: null,
                status: null
            },
            positionsBody: null
        };
    }

    async init() {
        console.log("[DriftController] Initializing Risk-First Engine...");

        // Cache DOM Elements
        this.els.gauge.needle = document.getElementById('health-needle');
        this.els.gauge.value = document.getElementById('drift-health-pct');
        this.els.gauge.container = document.getElementById('drift-health-gauge');

        this.els.metrics.total = document.getElementById('drift-total-collateral');
        this.els.metrics.free = document.getElementById('drift-free-collateral');
        this.els.metrics.maint = document.getElementById('drift-maint-margin');

        this.els.leverage.fill = document.getElementById('drift-leverage-fill');
        this.els.leverage.value = document.getElementById('drift-current-leverage');

        this.els.delta.val = document.getElementById('drift-delta-value');
        this.els.delta.status = document.getElementById('drift-delta-status');

        this.els.positionsBody = document.getElementById('drift-positions-body');

        // Bind Controls
        this._bindControls();

        this.initialized = true;
    }

    _bindControls() {
        // Subaccount Selector
        const subAccSelect = document.getElementById('drift-subaccount-select');
        if (subAccSelect) {
            subAccSelect.addEventListener('change', (e) => {
                this.activeSubAccount = parseInt(e.target.value);
                console.log(`[Drift] Switched to Sub-Account ${this.activeSubAccount}`);
                this._requestAccountUpdate();
            });
        }

        // Refresh Button
        const refreshBtn = document.getElementById('drift-refresh-markets-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                refreshBtn.querySelector('i').classList.add('spinning');
                setTimeout(() => refreshBtn.querySelector('i').classList.remove('spinning'), 1000);
            });
        }

        // Deposit Button
        const depositBtn = document.getElementById('drift-deposit-btn');
        if (depositBtn) {
            depositBtn.addEventListener('click', () => {
                const amount = prompt("Enter amount to DEPOSIT (SOL):");
                if (amount && !isNaN(amount)) {
                    window.tradingOS.ws.send('DRIFT_DEPOSIT', { amount: parseFloat(amount) });
                }
            });
        }

        // Withdraw Button
        const withdrawBtn = document.getElementById('drift-withdraw-btn');
        if (withdrawBtn) {
            withdrawBtn.addEventListener('click', () => {
                const amount = prompt("Enter amount to WITHDRAW (SOL):");
                if (amount && !isNaN(amount)) {
                    window.tradingOS.ws.send('DRIFT_WITHDRAW', { amount: parseFloat(amount) });
                }
            });
        }

        // Close All Button
        const closeAllBtn = document.getElementById('drift-close-all-btn');
        if (closeAllBtn) {
            closeAllBtn.addEventListener('click', () => {
                if (confirm("Are you sure you want to CLOSE ALL positions?")) {
                    window.tradingOS.ws.send('DRIFT_CLOSE_POSITION', { market: 'ALL' });
                }
            });
        }

        // Global Action for Rows
        window.closeDriftPosition = (market) => {
            if (confirm(`Close position for ${market}?`)) {
                window.tradingOS.ws.send('DRIFT_CLOSE_POSITION', { market: market });
            }
        };
    }

    /**
     * Ingest Real-Time System Stats
     * @param {Object} stats - The SYSTEM_STATS payload
     */
    update(stats) {
        if (!this.initialized) return;

        // Extract Drift-Specific Data
        // Expecting stats.vaults.drift OR stats.engines.drift OR stats.vaults.funding
        // Or specific drift_state packet
        const driftData = stats.drift_state ||
            (stats.vaults && stats.vaults.drift) ||
            (stats.vaults && stats.vaults.funding);

        if (!driftData) return;

        this._updateHealthGauge(driftData);
        this._updatePositions(driftData.positions || []);
        this._updateLeverage(driftData);
        this._updateDelta(driftData);
    }

    _updateHealthGauge(data) {
        // Calculate Health: 100% - (MaintMargin / TotalCollateral)
        // If Maint > Total, Health = 0 (Liquidation)

        const total = data.total_collateral || data.equity || 1; // Avoid div0
        const maint = data.maintenance_margin || 0;

        // Safety ratio
        const marginRatio = maint / total;
        let health = Math.max(0, Math.min(100, (1 - marginRatio) * 100));

        // Visual Rotation (Active Range: -120deg to +120deg? No, SVG is simple arc)
        // SVG Needle: 100,100 center. 
        // 0% Health (Left) -> -60deg
        // 50% Health (Top) -> 0deg
        // 100% Health (Right) -> +60deg
        // Let's calibrate based on the SVG path provided in HTML.
        // Arc goes from 100,100 radial?
        // Actually simpler: 0% = -90deg, 100% = +90deg ?
        // Let's assume linear mapping for now: range -90 (danger) to +90 (safe).

        const rotation = (health / 100) * 180 - 90; // -90 to +90

        if (this.els.gauge.needle) {
            this.els.gauge.needle.style.transform = `rotate(${rotation}deg)`;
        }

        if (this.els.gauge.value) {
            this.els.gauge.value.textContent = `${health.toFixed(0)}%`;

            // Color Classes
            const container = this.els.gauge.container;
            container.classList.remove('safe', 'warning', 'danger');

            if (health > 50) container.classList.add('safe');
            else if (health > 20) container.classList.add('warning');
            else container.classList.add('danger');
        }

        // Metrics
        this._setText(this.els.metrics.total, this._formatUSD(total));
        this._setText(this.els.metrics.free, this._formatUSD(data.free_collateral || 0));
        this._setText(this.els.metrics.maint, this._formatUSD(maint));
    }

    _updatePositions(positions) {
        const tbody = this.els.positionsBody;
        if (!tbody) return;

        tbody.innerHTML = '';

        if (!positions || positions.length === 0) {
            tbody.innerHTML = `<tr class="empty-row"><td colspan="8" class="empty-state">No open positions</td></tr>`;
            return;
        }

        positions.forEach(pos => {
            const isLong = pos.amount > 0;
            const sideClass = isLong ? 'side-long' : 'side-short';
            const sideText = isLong ? 'LONG' : 'SHORT';

            const pnlClass = pos.pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
            const pnlSign = pos.pnl >= 0 ? '+' : '';

            const row = document.createElement('tr');
            row.innerHTML = `
                <td style="font-weight: bold;">${pos.market}</td>
                <td class="${sideClass}">${sideText}</td>
                <td>${Math.abs(pos.amount).toFixed(3)}</td>
                <td>${pos.entry_price.toFixed(4)}</td>
                <td>${pos.mark_price.toFixed(4)}</td>
                <td class="${pnlClass}">${pnlSign}$${Math.abs(pos.pnl).toFixed(2)}</td>
                <td style="color: var(--neon-red);">${pos.liq_price > 0 ? pos.liq_price.toFixed(4) : '--'}</td>
                <td>
                    <button class="btn-close-position" onclick="window.closeDriftPosition('${pos.market}')">Close</button>
                </td>
            `;
            tbody.appendChild(row);
        });
    }

    _updateLeverage(data) {
        const lev = data.leverage || 0;
        const max = 20; // Cap visual at 20x

        const pct = Math.min(100, (lev / max) * 100);

        if (this.els.leverage.fill) {
            this.els.leverage.fill.style.width = `${pct}%`;
        }

        if (this.els.leverage.value) {
            this.els.leverage.value.textContent = `${lev.toFixed(1)}x`;
        }
    }

    _updateDelta(data) {
        const delta = data.net_delta || 0;
        if (this.els.delta.val) this.els.delta.val.textContent = delta.toFixed(2);

        if (this.els.delta.status) {
            // Neutral Threshold: +/- 0.5 SOL
            const absDelta = Math.abs(delta);
            this.els.delta.status.className = 'delta-status';

            if (absDelta < 0.5) {
                this.els.delta.status.classList.add('neutral');
                this.els.delta.status.textContent = 'NEUTRAL';
            } else if (absDelta < 2.0) {
                this.els.delta.status.classList.add('drifting');
                this.els.delta.status.textContent = 'DRIFTING';
            } else {
                this.els.delta.status.classList.add('critical');
                this.els.delta.status.textContent = 'EXPOSED';
            }
        }
    }

    _requestAccountUpdate() {
        // Emit socket event to request full account sync
        // window.socket.emit('drift_sync', { subaccount: this.activeSubAccount });
    }

    _formatUSD(val) {
        return '$' + val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    _setText(el, text) {
        if (el) el.textContent = text;
    }
}
