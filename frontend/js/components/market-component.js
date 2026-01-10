/**
 * Market Components
 * =================
 * Specialized data views for each trading engine.
 */

export class MarketComponent {
    constructor(engineName, containerId) {
        this.engineName = engineName;
        this.container = document.querySelector(containerId) ||
            document.querySelector(`.engine-card[data-engine="${engineName}"] .card-body`);

        if (this.container) {
            this.render();
        }
    }

    render() {
        // Base render method to be overridden
    }

    update(data) {
        // Base update method
    }
}

/**
 * Arb Scanner View
 * Displays top arbitrage spreads.
 */
export class ArbScanner extends MarketComponent {
    render() {
        this.container.innerHTML = `
            <div class="market-view arb-view">
                <div class="view-header">
                    <span class="view-title">TOP SPREADS</span>
                    <label class="switch-toggle mini" title="Scanner Active">
                        <input type="checkbox" checked class="component-toggle">
                        <span class="slider round"></span>
                    </label>
                </div>
                <div class="spread-list" id="arb-spread-list">
                    <div class="empty-state">Scanning markets...</div>
                </div>
            </div>
        `;
        this.list = this.container.querySelector('#arb-spread-list');
    }

    update(opp) {
        if (!this.list) return;

        // Remove empty state
        if (this.list.querySelector('.empty-state')) {
            this.list.innerHTML = '';
        }

        const item = document.createElement('div');
        item.className = 'spread-item';
        item.innerHTML = `
            <div class="pair-info">
                <span class="token">${opp.token || 'SOL'}</span>
                <span class="route">${opp.buy_venue?.slice(0, 3)} → ${opp.sell_venue?.slice(0, 3)}</span>
            </div>
            <div class="spread-value positive">+${(opp.spread || 0).toFixed(2)}%</div>
        `;

        // Prepend and limit to 5 items
        this.list.insertBefore(item, this.list.firstChild);
        if (this.list.children.length > 5) {
            this.list.removeChild(this.list.lastChild);
        }
    }
}

/**
 * Funding Monitor View
 * Displays current yield rates.
 */
export class FundingMonitor extends MarketComponent {
    render() {
        this.container.innerHTML = `
            <div class="market-view funding-view">
                <div class="view-header">
                    <span class="view-title">YIELD GAUGE</span>
                    <label class="switch-toggle mini" title="Monitor Active">
                        <input type="checkbox" checked class="component-toggle">
                        <span class="slider round"></span>
                    </label>
                </div>
                <div class="yield-display">
                    <div class="yield-metric">
                        <span class="label">Current APR</span>
                        <span class="value" id="funding-apr">--%</span>
                    </div>
                    <div class="yield-metric">
                        <span class="label">Next Payment</span>
                        <span class="value" id="funding-next">--</span>
                    </div>
                </div>
            </div>
        `;
    }

    update(data) {
        const aprEl = this.container.querySelector('#funding-apr');
        if (aprEl && data.apr) aprEl.textContent = `${data.apr.toFixed(2)}%`;
    }
}

/**
 * Scalp Pods View
 * Displays active signal pods and sentiment.
 */
export class ScalpPods extends MarketComponent {
    render() {
        this.container.innerHTML = `
            <div class="market-view scalp-view">
                <div class="view-header">
                    <span class="view-title">ACTIVE PODS</span>
                    <label class="switch-toggle mini" title="Pods Active">
                        <input type="checkbox" checked class="component-toggle">
                        <span class="slider round"></span>
                    </label>
                </div>
                <div class="pod-grid" id="scalp-pod-grid">
                    <div class="empty-state">Waiting for signals...</div>
                </div>
            </div>
        `;
        this.grid = this.container.querySelector('#scalp-pod-grid');
    }

    update(signal) {
        if (!this.grid) return;

        if (this.grid.querySelector('.empty-state')) {
            this.grid.innerHTML = '';
        }

        // Check if pod exists for token
        let pod = this.grid.querySelector(`.pod-item[data-token="${signal.token}"]`);

        if (!pod) {
            pod = document.createElement('div');
            pod.className = 'pod-item';
            pod.dataset.token = signal.token;
            this.grid.appendChild(pod);
        }

        const sentimentClass = signal.sentiment > 0.6 ? 'bullish' : (signal.sentiment < 0.4 ? 'bearish' : 'neutral');

        pod.innerHTML = `
            <div class="pod-header">
                <span class="token">${signal.token}</span>
                <span class="confidence">${(signal.confidence * 100).toFixed(0)}%</span>
            </div>
            <div class="pod-sentiment ${sentimentClass}">
                ${signal.action}
            </div>
        `;
    }
}

/**
 * LST Monitor View
 * Displays LST/SOL pegs and alerts on discounts.
 */
export class LstMonitor extends MarketComponent {
    render() {
        this.container.innerHTML = `
            <div class="market-view lst-view">
                <div class="view-header">
                    <span class="view-title">FAIR VALUE MONITOR</span>
                    <span class="status-indicator safe" id="lst-global-status">SAFE</span>
                </div>
                <div class="lst-grid" id="lst-grid">
                    <!-- Injected rows -->
                </div>
            </div>
        `;
        this.grid = this.container.querySelector('#lst-grid');
        this.status = this.container.querySelector('#lst-global-status');

        // Initial View
        this.update({
            "jitoSOL": { price: 1.072, fair: 1.072, diff: 0 },
            "mSOL": { price: 1.145, fair: 1.145, diff: 0 }
        });
    }

    update(data) {
        if (!this.grid) return;
        this.grid.innerHTML = '';

        let anyDepeg = false;

        Object.entries(data).forEach(([token, stats]) => {
            const isDepeg = stats.diff <= -0.005;
            if (isDepeg) anyDepeg = true;

            const row = document.createElement('div');
            row.className = `lst-row ${isDepeg ? 'danger' : ''}`;
            row.innerHTML = `
                <div class="token-name">${token}</div>
                <div class="token-price">${stats.price.toFixed(4)}</div>
                <div class="token-diff ${isDepeg ? 'alert' : ''}">${(stats.diff * 100).toFixed(2)}%</div>
            `;
            this.grid.appendChild(row);
        });

        if (this.status) {
            this.status.textContent = anyDepeg ? 'DE-PEG ALERT' : 'PEG STABLE';
            this.status.className = `status-indicator ${anyDepeg ? 'danger' : 'safe'}`;
        }
    }
}
