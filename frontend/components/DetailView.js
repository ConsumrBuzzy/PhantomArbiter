/**
 * DetailView Navigation Controller
 * =================================
 * Manages transitions between Matrix (glance) and Detail (drill-down) views.
 * 
 * Architecture:
 * - Level 1: Matrix → All engines as compact cards
 * - Level 2: Detail → Full control room for selected engine
 * - Level 3: Vault  → Per-engine paper wallet controls
 */

export class NavigationController {

    constructor() {
        this.currentView = 'matrix';
        this.currentEngine = null;
        this.history = [];
        this.detailViews = new Map();

        // Register engine detail views
        this._registerViews();

        // Bind keyboard navigation
        this._bindKeyboard();
    }

    /**
     * Register detail view components for each engine type.
     */
    _registerViews() {
        this.detailViews.set('arb', ArbDetailView);
        this.detailViews.set('funding', FundingDetailView);
        this.detailViews.set('scalp', ScalpDetailView);
        this.detailViews.set('lst', LSTDetailView);
    }

    /**
     * Navigate to engine detail view.
     */
    navigateToDetail(engineId) {
        // Push current state to history
        this.history.push({
            view: this.currentView,
            engine: this.currentEngine,
        });

        this.currentView = 'detail';
        this.currentEngine = engineId;

        this._mountDetailView(engineId);
        this._updateURL(engineId);
    }

    /**
     * Navigate back to matrix view.
     */
    navigateToMatrix() {
        this.currentView = 'matrix';
        this.currentEngine = null;

        this._unmountDetailView();
        this._mountMatrixView();
        this._updateURL(null);
    }

    /**
     * Go back in history.
     */
    goBack() {
        if (this.history.length === 0) {
            this.navigateToMatrix();
            return;
        }

        const prev = this.history.pop();

        if (prev.view === 'matrix') {
            this.navigateToMatrix();
        } else {
            this.navigateToDetail(prev.engine);
        }
    }

    /**
     * Mount the detail view for an engine.
     */
    _mountDetailView(engineId) {
        const container = document.getElementById('main-content');
        if (!container) return;

        // Hide matrix
        const matrix = document.getElementById('engine-matrix');
        if (matrix) matrix.style.display = 'none';

        // Get or create detail container
        let detailContainer = document.getElementById('detail-container');
        if (!detailContainer) {
            detailContainer = document.createElement('div');
            detailContainer.id = 'detail-container';
            container.appendChild(detailContainer);
        }

        detailContainer.style.display = 'block';

        // Get view class and mount
        const ViewClass = this.detailViews.get(engineId);
        if (ViewClass) {
            const view = new ViewClass(detailContainer, engineId);
            view.mount();
            this._activeView = view;
        }
    }

    /**
     * Unmount current detail view.
     */
    _unmountDetailView() {
        if (this._activeView && this._activeView.unmount) {
            this._activeView.unmount();
        }

        const detailContainer = document.getElementById('detail-container');
        if (detailContainer) {
            detailContainer.style.display = 'none';
            detailContainer.innerHTML = '';
        }
    }

    /**
     * Mount the matrix view.
     */
    _mountMatrixView() {
        const matrix = document.getElementById('engine-matrix');
        if (matrix) matrix.style.display = 'grid';
    }

    /**
     * Update browser URL for deep linking.
     */
    _updateURL(engineId) {
        const url = engineId
            ? `/engine/${engineId}`
            : '/';

        window.history.pushState({ engineId }, '', url);
    }

    /**
     * Bind keyboard shortcuts.
     */
    _bindKeyboard() {
        document.addEventListener('keydown', (e) => {
            // Escape → go back
            if (e.key === 'Escape') {
                this.goBack();
            }

            // Number keys 1-4 → quick nav to engines
            if (this.currentView === 'matrix') {
                const engineMap = { '1': 'arb', '2': 'funding', '3': 'scalp', '4': 'lst' };
                if (engineMap[e.key]) {
                    this.navigateToDetail(engineMap[e.key]);
                }
            }
        });

        // Handle browser back button
        window.addEventListener('popstate', (e) => {
            if (e.state && e.state.engineId) {
                this._mountDetailView(e.state.engineId);
            } else {
                this.navigateToMatrix();
            }
        });
    }
}


/**
 * ArbDetailView
 * =============
 * Full control room for the Arbitrage Engine.
 * 
 * Features:
 * - Triangular path visualization
 * - Manual fee override sliders
 * - Recent opportunity log
 * - Paper vault controls
 */
export class ArbDetailView {

    constructor(container, engineId) {
        this.container = container;
        this.engineId = engineId;
        this.ws = null;
    }

    mount() {
        this.container.innerHTML = this._template();
        this._bindEvents();
        this._connectWebSocket();
    }

    unmount() {
        if (this.ws) {
            this.ws.close();
        }
    }

    _template() {
        return `
            <div class="detail-view arb-detail">
                <header class="detail-header">
                    <button class="back-btn" id="back-btn">← Back</button>
                    <h1 class="detail-title">🔺 Arbitrage Engine</h1>
                    <div class="engine-status-badge running">RUNNING</div>
                </header>
                
                <div class="detail-grid">
                    <!-- Left Column: Path Visualization -->
                    <section class="path-section">
                        <h2>Active Path</h2>
                        <div class="path-canvas" id="path-canvas">
                            <svg id="path-svg" viewBox="0 0 400 350"></svg>
                        </div>
                        <div class="path-info">
                            <div class="path-stat">
                                <span class="label">Best Spread</span>
                                <span class="value" id="best-spread">0.00%</span>
                            </div>
                            <div class="path-stat">
                                <span class="label">Path</span>
                                <span class="value" id="path-tokens">--</span>
                            </div>
                        </div>
                    </section>
                    
                    <!-- Right Column: Controls -->
                    <section class="controls-section">
                        <h2>Fee Overrides</h2>
                        <div class="control-group">
                            <label>Min Spread Threshold</label>
                            <input type="range" id="min-spread" min="0.1" max="2.0" step="0.05" value="0.5">
                            <span id="min-spread-value">0.50%</span>
                        </div>
                        <div class="control-group">
                            <label>Max Slippage</label>
                            <input type="range" id="max-slippage" min="0.1" max="3.0" step="0.1" value="1.0">
                            <span id="max-slippage-value">1.00%</span>
                        </div>
                        <div class="control-group">
                            <label>Jito Tip (Lamports)</label>
                            <input type="number" id="jito-tip" min="1000" max="100000" value="10000">
                        </div>
                        
                        <h2>Paper Vault</h2>
                        <div class="vault-summary" id="arb-vault">
                            <div class="vault-balance">$50.00</div>
                            <div class="vault-pnl positive">+$2.35</div>
                        </div>
                        <div class="vault-actions">
                            <button class="btn-secondary" id="reset-vault">Reset Sim</button>
                            <button class="btn-primary" id="exec-trade">Execute Trade</button>
                        </div>
                    </section>
                </div>
                
                <!-- Bottom: Opportunity Log -->
                <section class="opportunity-log">
                    <h2>Recent Opportunities</h2>
                    <table class="opp-table">
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Path</th>
                                <th>Spread</th>
                                <th>Est. Profit</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody id="opp-log-body">
                            <tr class="empty-row">
                                <td colspan="5">Scanning for opportunities...</td>
                            </tr>
                        </tbody>
                    </table>
                </section>
            </div>
        `;
    }

    _bindEvents() {
        // Back button
        document.getElementById('back-btn')?.addEventListener('click', () => {
            window.navigation?.navigateToMatrix();
        });

        // Sliders
        const minSpread = document.getElementById('min-spread');
        minSpread?.addEventListener('input', (e) => {
            document.getElementById('min-spread-value').textContent = `${e.target.value}%`;
        });

        const maxSlippage = document.getElementById('max-slippage');
        maxSlippage?.addEventListener('input', (e) => {
            document.getElementById('max-slippage-value').textContent = `${e.target.value}%`;
        });

        // Reset vault
        document.getElementById('reset-vault')?.addEventListener('click', () => {
            this._resetVault();
        });
    }

    _connectWebSocket() {
        // Connect to arb-specific endpoint
        const host = window.location.host || 'localhost:8001';
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

        this.ws = new WebSocket(`${protocol}//${host}/ws/v1/engine/arb`);

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this._updateFromPayload(data);
        };
    }

    _updateFromPayload(data) {
        // Update spread
        if (data.best_spread !== undefined) {
            document.getElementById('best-spread').textContent =
                `${data.best_spread.toFixed(2)}%`;
        }

        // Update path tokens
        if (data.path) {
            document.getElementById('path-tokens').textContent =
                data.path.join(' → ');
            this._drawPath(data.path, data.prices);
        }

        // Update vault
        if (data.vault) {
            const vaultEl = document.getElementById('arb-vault');
            vaultEl.querySelector('.vault-balance').textContent =
                `$${data.vault.equity.toFixed(2)}`;
            vaultEl.querySelector('.vault-pnl').textContent =
                `${data.vault.pnl >= 0 ? '+' : ''}$${data.vault.pnl.toFixed(2)}`;
        }

        // Add to opportunity log
        if (data.opportunity) {
            this._addOpportunityRow(data.opportunity);
        }
    }

    _drawPath(tokens, prices = {}) {
        const svg = document.getElementById('path-svg');
        if (!svg || tokens.length < 3) return;

        // Triangle coordinates
        const points = [
            { x: 200, y: 50 },   // Top
            { x: 50, y: 300 },   // Bottom left
            { x: 350, y: 300 },  // Bottom right
        ];

        svg.innerHTML = `
            <!-- Triangle path -->
            <path d="M ${points[0].x} ${points[0].y} 
                     L ${points[1].x} ${points[1].y} 
                     L ${points[2].x} ${points[2].y} Z"
                  fill="none" 
                  stroke="rgba(168, 85, 247, 0.5)" 
                  stroke-width="2"/>
            
            <!-- Animated flow -->
            <circle r="5" fill="#a855f7">
                <animateMotion dur="2s" repeatCount="indefinite" 
                    path="M ${points[0].x} ${points[0].y} 
                          L ${points[1].x} ${points[1].y} 
                          L ${points[2].x} ${points[2].y} Z"/>
            </circle>
            
            <!-- Token labels -->
            ${tokens.map((token, i) => `
                <g transform="translate(${points[i].x}, ${points[i].y})">
                    <circle r="25" fill="#1e1e2e" stroke="#a855f7" stroke-width="2"/>
                    <text text-anchor="middle" dy="5" fill="#fff" font-size="12">${token}</text>
                </g>
            `).join('')}
        `;
    }

    _addOpportunityRow(opp) {
        const tbody = document.getElementById('opp-log-body');
        if (!tbody) return;

        // Remove empty row if present
        tbody.querySelector('.empty-row')?.remove();

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${new Date(opp.timestamp).toLocaleTimeString()}</td>
            <td>${opp.path.join(' → ')}</td>
            <td>${opp.spread.toFixed(2)}%</td>
            <td class="profit">+$${opp.profit.toFixed(2)}</td>
            <td><span class="status-badge ${opp.status.toLowerCase()}">${opp.status}</span></td>
        `;

        // Add to top
        tbody.insertBefore(row, tbody.firstChild);

        // Keep max 20 rows
        while (tbody.children.length > 20) {
            tbody.removeChild(tbody.lastChild);
        }
    }

    _resetVault() {
        // Send reset command
        fetch('/api/v1/vault/arb/reset', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                console.log('Vault reset:', data);
            });
    }
}


/**
 * Placeholder views for other engines
 */
class FundingDetailView {
    constructor(container) { this.container = container; }
    mount() { this.container.innerHTML = '<h1>Funding Engine (Coming Soon)</h1>'; }
    unmount() { }
}

class ScalpDetailView {
    constructor(container) { this.container = container; }
    mount() { this.container.innerHTML = '<h1>Scalp Engine (Coming Soon)</h1>'; }
    unmount() { }
}

class LSTDetailView {
    constructor(container) { this.container = container; }
    mount() { this.container.innerHTML = '<h1>LST Engine (Coming Soon)</h1>'; }
    unmount() { }
}


// Global navigation instance
window.navigation = new NavigationController();
