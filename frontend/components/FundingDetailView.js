/**
 * FundingDetailView Component
 * ===========================
 * Full control room for the Delta-Neutral Funding Engine.
 * 
 * Features:
 * - Semi-circular delta-neutrality gauge
 * - Spot/Perp position displays
 * - Funding rate countdown and history
 * - Auto-rebalance controls
 */

export class FundingDetailView {

    constructor(container, engineId) {
        this.container = container;
        this.engineId = engineId;
        this.ws = null;

        // State
        this.deltaState = {
            drift_pct: 0,
            status: 'UNKNOWN',
            spot_qty: 0,
            perp_qty: 0,
        };
    }

    mount() {
        this.container.innerHTML = this._template();
        this._bindEvents();
        this._connectWebSocket();
        this._startCountdown();
    }

    unmount() {
        if (this.ws) this.ws.close();
        if (this._countdownInterval) clearInterval(this._countdownInterval);
    }

    _template() {
        return `
            <div class="detail-view funding-detail-page">
                <header class="detail-header">
                    <button class="back-btn" id="back-btn">← Back</button>
                    <h1 class="detail-title">⚖️ Delta-Neutral Engine</h1>
                    <div class="engine-status-badge running">HEDGED</div>
                </header>
                
                <div class="funding-detail">
                    <!-- Delta Gauge -->
                    <div class="delta-gauge-container">
                        <div class="gauge-title">Delta Neutrality</div>
                        <div class="delta-gauge">
                            <div class="gauge-background"></div>
                            <div class="gauge-needle" id="gauge-needle"></div>
                            <div class="gauge-labels">
                                <span class="gauge-label left">-5%</span>
                                <span class="gauge-label center">0%</span>
                                <span class="gauge-label right">+5%</span>
                            </div>
                        </div>
                        <div class="gauge-value">
                            <span class="number" id="drift-value">0.0</span>
                            <span class="unit">%</span>
                            <div class="status balanced" id="drift-status">BALANCED</div>
                        </div>
                    </div>
                    
                    <!-- Funding Rate -->
                    <div class="funding-rate-panel">
                        <div class="rate-header">
                            <span class="rate-title">Current Rate (8h)</span>
                            <span class="rate-countdown" id="rate-countdown">--:--:--</span>
                        </div>
                        <div class="rate-value positive" id="funding-rate">+0.0100%</div>
                        <div class="rate-annualized">
                            Annualized: <span id="rate-apy">~36.5%</span>
                        </div>
                    </div>
                    
                    <!-- Spot Position -->
                    <div class="position-card long">
                        <h3>Long Spot (SOL)</h3>
                        <div class="position-value" id="spot-qty">0.0000 SOL</div>
                        <div class="position-sub" id="spot-value">$0.00</div>
                    </div>
                    
                    <!-- Perp Position -->
                    <div class="position-card short">
                        <h3>Short Perp (SOL-PERP)</h3>
                        <div class="position-value" id="perp-qty">0.0000 SOL</div>
                        <div class="position-sub" id="perp-value">$0.00</div>
                    </div>
                    
                    <!-- Rebalance Controls -->
                    <div class="rebalance-panel">
                        <div class="rebalance-header">
                            <span class="rebalance-title">Rebalance Controls</span>
                            <div class="auto-toggle">
                                <label>Auto-Rebalance</label>
                                <div class="toggle-switch">
                                    <input type="checkbox" id="auto-rebalance">
                                    <span class="toggle-slider"></span>
                                </div>
                            </div>
                        </div>
                        
                        <div class="threshold-row">
                            <span class="threshold-label">Drift Threshold</span>
                            <input type="range" class="threshold-slider" id="drift-threshold" 
                                   min="0.5" max="5.0" step="0.1" value="2.0">
                            <span class="threshold-value" id="drift-threshold-value">2.0%</span>
                        </div>
                        
                        <div class="threshold-row">
                            <span class="threshold-label">Min Funding Rate</span>
                            <input type="range" class="threshold-slider" id="min-funding" 
                                   min="0" max="0.05" step="0.001" value="0.005">
                            <span class="threshold-value" id="min-funding-value">0.50%</span>
                        </div>
                        
                        <div class="rebalance-actions">
                            <button class="btn-rebalance add-short" id="btn-add-short" disabled>
                                Add Short Position
                            </button>
                            <button class="btn-rebalance reduce-short" id="btn-reduce-short" disabled>
                                Reduce Short Position
                            </button>
                        </div>
                    </div>
                    
                    <!-- Funding History -->
                    <div class="position-card funding-history">
                        <h3>Recent Payments</h3>
                        <table class="history-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Rate</th>
                                    <th>Payment</th>
                                    <th>Cumulative</th>
                                </tr>
                            </thead>
                            <tbody id="funding-history-body">
                                <tr><td colspan="4" style="text-align:center;color:#64748b">Loading...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;
    }

    _bindEvents() {
        // Back button
        document.getElementById('back-btn')?.addEventListener('click', () => {
            window.navigation?.navigateToMatrix();
        });

        // Drift threshold slider
        const driftSlider = document.getElementById('drift-threshold');
        driftSlider?.addEventListener('input', (e) => {
            document.getElementById('drift-threshold-value').textContent = `${e.target.value}%`;
        });

        // Min funding slider
        const fundingSlider = document.getElementById('min-funding');
        fundingSlider?.addEventListener('input', (e) => {
            const pct = (parseFloat(e.target.value) * 100).toFixed(2);
            document.getElementById('min-funding-value').textContent = `${pct}%`;
        });

        // Rebalance buttons
        document.getElementById('btn-add-short')?.addEventListener('click', () => {
            this._executeRebalance('ADD_SHORT');
        });

        document.getElementById('btn-reduce-short')?.addEventListener('click', () => {
            this._executeRebalance('REDUCE_SHORT');
        });
    }

    _connectWebSocket() {
        const host = window.location.host || 'localhost:8001';
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

        this.ws = new WebSocket(`${protocol}//${host}/ws/v1/engine/funding`);

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this._updateFromPayload(data);
        };
    }

    _updateFromPayload(data) {
        // Update delta state
        if (data.delta_state) {
            this.deltaState = data.delta_state;
            this._updateGauge(data.delta_state.drift_pct);
            this._updateStatus(data.delta_state.status);
            this._updatePositions(data.delta_state);
            this._updateRebalanceButtons(data.delta_state);
        }

        // Update funding rate
        if (data.funding_rate !== undefined) {
            this._updateFundingRate(data.funding_rate);
        }

        // Update history
        if (data.funding_history) {
            this._updateHistory(data.funding_history);
        }
    }

    _updateGauge(driftPct) {
        const needle = document.getElementById('gauge-needle');
        const valueEl = document.getElementById('drift-value');

        if (needle) {
            // Convert drift to angle: -5% = -90deg, 0% = 0deg, +5% = 90deg
            const clampedDrift = Math.max(-5, Math.min(5, driftPct));
            const angle = (clampedDrift / 5) * 90;
            needle.style.transform = `translateX(-50%) rotate(${angle}deg)`;
        }

        if (valueEl) {
            valueEl.textContent = driftPct.toFixed(1);
        }
    }

    _updateStatus(status) {
        const statusEl = document.getElementById('drift-status');
        const badge = document.querySelector('.engine-status-badge');

        if (statusEl) {
            statusEl.textContent = status;
            statusEl.className = 'status';

            if (status === 'BALANCED') {
                statusEl.classList.add('balanced');
                if (badge) badge.textContent = 'HEDGED';
            } else if (status === 'CRITICAL') {
                statusEl.classList.add('critical');
                if (badge) badge.textContent = 'CRITICAL';
            } else {
                statusEl.classList.add('warning');
                if (badge) badge.textContent = 'DRIFTING';
            }
        }
    }

    _updatePositions(delta) {
        const spotQty = document.getElementById('spot-qty');
        const spotValue = document.getElementById('spot-value');
        const perpQty = document.getElementById('perp-qty');
        const perpValue = document.getElementById('perp-value');

        if (spotQty) spotQty.textContent = `${delta.spot_qty.toFixed(4)} SOL`;
        if (spotValue) spotValue.textContent = `$${delta.spot_exposure_usd?.toFixed(2) || '0.00'}`;
        if (perpQty) perpQty.textContent = `${Math.abs(delta.perp_qty).toFixed(4)} SOL`;
        if (perpValue) perpValue.textContent = `$${Math.abs(delta.perp_exposure_usd || 0).toFixed(2)}`;
    }

    _updateRebalanceButtons(delta) {
        const addShort = document.getElementById('btn-add-short');
        const reduceShort = document.getElementById('btn-reduce-short');

        if (delta.suggested_action === 'ADD_SHORT') {
            addShort.disabled = false;
            reduceShort.disabled = true;
        } else if (delta.suggested_action === 'REDUCE_SHORT') {
            addShort.disabled = true;
            reduceShort.disabled = false;
        } else {
            addShort.disabled = true;
            reduceShort.disabled = true;
        }
    }

    _updateFundingRate(rate) {
        const rateEl = document.getElementById('funding-rate');
        const apyEl = document.getElementById('rate-apy');

        if (rateEl) {
            const pct = (rate * 100).toFixed(4);
            rateEl.textContent = `${rate >= 0 ? '+' : ''}${pct}%`;
            rateEl.className = `rate-value ${rate >= 0 ? 'positive' : 'negative'}`;
        }

        if (apyEl) {
            // 3 payments per day * 365 days
            const apy = rate * 3 * 365 * 100;
            apyEl.textContent = `~${apy.toFixed(1)}%`;
        }
    }

    _updateHistory(history) {
        const tbody = document.getElementById('funding-history-body');
        if (!tbody) return;

        let cumulative = 0;
        const rows = history.slice(0, 10).map(h => {
            cumulative += h.payment;
            const isPositive = h.payment >= 0;
            return `
                <tr>
                    <td>${new Date(h.timestamp).toLocaleTimeString()}</td>
                    <td>${(h.rate * 100).toFixed(4)}%</td>
                    <td class="${isPositive ? 'collected' : 'paid'}">
                        ${isPositive ? '+' : ''}$${h.payment.toFixed(4)}
                    </td>
                    <td>$${cumulative.toFixed(4)}</td>
                </tr>
            `;
        }).join('');

        tbody.innerHTML = rows || '<tr><td colspan="4">No history</td></tr>';
    }

    _startCountdown() {
        const update = () => {
            const now = new Date();
            const nextPayment = new Date(now);

            // Next 8-hour mark (0, 8, 16 UTC)
            const hourOfDay = now.getUTCHours();
            const nextHour = Math.ceil(hourOfDay / 8) * 8;
            nextPayment.setUTCHours(nextHour, 0, 0, 0);

            if (nextPayment <= now) {
                nextPayment.setUTCHours(nextPayment.getUTCHours() + 8);
            }

            const diff = nextPayment - now;
            const hours = Math.floor(diff / 3600000);
            const minutes = Math.floor((diff % 3600000) / 60000);
            const seconds = Math.floor((diff % 60000) / 1000);

            const el = document.getElementById('rate-countdown');
            if (el) {
                el.textContent =
                    `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }
        };

        update();
        this._countdownInterval = setInterval(update, 1000);
    }

    _executeRebalance(action) {
        fetch('/api/v1/engine/funding/rebalance', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action }),
        })
            .then(res => res.json())
            .then(data => {
                console.log('Rebalance:', data);
            });
    }
}
