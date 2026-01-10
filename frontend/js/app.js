/**
 * Phantom Arbiter - Trading OS Control Logic
 * ===========================================
 * V21: Bidirectional WebSocket Command Center
 * 
 * Features:
 * - Engine lifecycle control (start/stop/restart)
 * - Real-time engine status updates
 * - Settings modal with dynamic forms
 * - SOS emergency stop
 * - View navigation (Dashboard/Engines/Config)
 */

class DashboardApp {
    constructor() {
        this.ws = null;
        this.maxLogs = 50;

        // DOM Elements
        this.logStream = document.getElementById('log-stream');
        this.intelTableBody = document.querySelector('#intel-table tbody');
        this.inventoryTableBody = document.querySelector('#inventory-table tbody');
        this.engineMode = document.getElementById('engine-mode');
        this.statsLatency = document.getElementById('stats-latency');
        this.statsPnl = document.getElementById('stats-pnl');
        this.statsEngines = document.getElementById('stats-engines');

        // Engine state cache
        this.engineStates = {};

        // Engine execution modes (paper/live per engine)
        this.engineModes = {
            arb: 'paper',
            funding: 'paper',
            scalp: 'paper'
        };

        // Currently editing engine
        this.editingEngine = null;

        // Initialize
        this.bindEvents();
        this.connect();
    }

    /**
     * Bind all UI event listeners
     */
    bindEvents() {
        // Navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => this.switchView(item.dataset.view));
        });

        // Power toggles
        document.querySelectorAll('.power-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleEngine(btn.dataset.engine);
            });
        });

        // Settings buttons
        document.querySelectorAll('.settings-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.openSettingsModal(btn.dataset.engine);
            });
        });

        // Mode selector buttons
        document.querySelectorAll('.mode-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.setEngineMode(btn.closest('.mode-selector').dataset.engine, btn.dataset.mode);
            });
        });

        // SOS Button
        document.getElementById('sos-btn').addEventListener('click', () => {
            this.openSOSModal();
        });

        // Modal close buttons
        document.querySelectorAll('.modal-close, [data-action="cancel"]').forEach(btn => {
            btn.addEventListener('click', () => this.closeAllModals());
        });

        // Settings save
        document.querySelector('[data-action="save"]')?.addEventListener('click', () => {
            this.saveEngineConfig();
        });

        // SOS confirm
        document.querySelector('[data-action="confirm-sos"]')?.addEventListener('click', () => {
            this.executeSOS();
        });

        // Close modals on overlay click
        document.querySelectorAll('.modal-overlay').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) this.closeAllModals();
            });
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeAllModals();
        });
    }

    /**
     * Switch between views (Dashboard/Engines/Config)
     */
    switchView(viewName) {
        // Update nav items
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.view === viewName);
        });

        // Update view panels
        document.querySelectorAll('.view-panel').forEach(panel => {
            panel.classList.toggle('active', panel.id === `view-${viewName}`);
        });
    }

    /**
     * WebSocket Connection
     */
    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname || 'localhost';
        const port = 8765;
        const url = `${protocol}//${host}:${port}`;

        this.addLog('SYSTEM', 'INFO', `Connecting to Command Center: ${url}...`);

        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            this.addLog('SYSTEM', 'SUCCESS', '🎮 Command Center Linked');
            this.engineMode.textContent = 'LINKED';
            this.engineMode.style.color = 'var(--neon-green)';

            // Request initial status
            this.sendCommand('GET_STATUS');
        };

        this.ws.onmessage = (event) => {
            try {
                const packet = JSON.parse(event.data);
                this.handlePacket(packet);
            } catch (e) {
                console.error("Parse error", e);
            }
        };

        this.ws.onclose = () => {
            this.addLog('SYSTEM', 'WARNING', 'Link Lost - Reconnecting in 3s...');
            this.engineMode.textContent = 'OFFLINE';
            this.engineMode.style.color = 'var(--neon-red)';
            setTimeout(() => this.connect(), 3000);
        };

        this.ws.onerror = (err) => {
            this.addLog('SYSTEM', 'ERROR', 'WebSocket Connection Error');
        };
    }

    /**
     * Send command to backend
     */
    sendCommand(action, payload = {}) {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ action, ...payload }));
        } else {
            this.addLog('SYSTEM', 'ERROR', 'Cannot send command - not connected');
        }
    }

    /**
     * Handle incoming packets
     */
    handlePacket(packet) {
        const { type, data } = packet;

        switch (type) {
            case 'SYSTEM_STATS':
                this.updateStats(data);
                break;

            case 'ENGINE_STATUS':
                this.updateEngineStates(data);
                break;

            case 'ENGINE_RESPONSE':
                this.handleEngineResponse(packet);
                break;

            case 'SOS_RESPONSE':
                this.handleSOSResponse(packet);
                break;

            case 'LOG_ENTRY':
                this.addLog(data.source, data.level, data.message, data.timestamp);
                break;

            case 'ARB_OPP':
                this.updateIntelTable('ARB', data);
                this.addToScanner('arb', data);
                break;

            case 'SCALP_SIGNAL':
                this.updateIntelTable('SCALP', data);
                this.addToScanner('scalp', data);
                break;

            case 'SCANNER_UPDATE':
                this.updateScanner(data);
                break;

            case 'MARKET_DATA':
                this.updateMarketData(data);
                break;

            case 'INVENTORY_UPDATE':
                this.updateInventory(data);
                break;

            default:
                // Unhandled packet type
                break;
        }
    }

    /**
     * Update system stats display
     */
    updateStats(stats) {
        if (stats.mode) {
            const mode = stats.mode.toUpperCase();
            this.engineMode.textContent = mode;
            this.updateLayoutForMode(mode);
        }

        if (stats.wss_latency_ms !== undefined) {
            this.statsLatency.textContent = `${stats.wss_latency_ms}ms`;
        }

        if (stats.settled_pnl !== undefined) {
            const val = stats.settled_pnl;
            this.statsPnl.textContent = `$${val.toFixed(2)}`;
            this.statsPnl.style.color = val >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
        }

        // Update engine states from heartbeat
        if (stats.engines) {
            this.updateEngineStates(stats.engines);
        }
    }

    /**
     * Update market data (live SOL price from Pyth)
     */
    updateMarketData(data) {
        const priceEl = document.getElementById('stats-sol-price');
        if (priceEl && data.sol_price) {
            priceEl.textContent = `$${data.sol_price.toFixed(2)}`;

            // Flash green on update
            priceEl.style.color = 'var(--neon-green)';
            setTimeout(() => {
                priceEl.style.color = 'var(--neon-blue)';
            }, 300);
        }
    }

    /**
     * Update all engine card states
     */
    updateEngineStates(engines) {
        this.engineStates = engines;

        let runningCount = 0;
        const totalCount = Object.keys(engines).length;

        Object.entries(engines).forEach(([name, state]) => {
            const card = document.querySelector(`.engine-card[data-engine="${name}"]`);
            if (!card) return;

            // Update status attribute
            card.dataset.status = state.status;

            // Update status text
            const statusText = card.querySelector('.status-text');
            if (statusText) {
                statusText.textContent = this.formatStatus(state.status);
            }

            // Update uptime
            const uptimeEl = card.querySelector('.status-uptime');
            if (uptimeEl && state.uptime_seconds) {
                uptimeEl.textContent = this.formatUptime(state.uptime_seconds);
            } else if (uptimeEl) {
                uptimeEl.textContent = '';
            }

            // Update config values
            if (state.config) {
                this.updateConfigDisplay(card, state.config);
            }

            if (state.status === 'running') runningCount++;
        });

        // Update header counter
        if (this.statsEngines) {
            this.statsEngines.textContent = `${runningCount}/${totalCount}`;
        }
    }

    /**
     * Format status for display
     */
    formatStatus(status) {
        const statusMap = {
            'stopped': 'Stopped',
            'starting': 'Starting...',
            'running': 'Running',
            'stopping': 'Stopping...',
            'error': 'Error'
        };
        return statusMap[status] || status;
    }

    /**
     * Format uptime duration
     */
    formatUptime(seconds) {
        if (seconds < 60) return `${Math.floor(seconds)}s`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
        return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
    }

    /**
     * Update config display in engine card
     */
    updateConfigDisplay(card, config) {
        const formatters = {
            'min_spread': (v) => `${v}%`,
            'max_trade_usd': (v) => `$${v}`,
            'scan_interval': (v) => `${v}s`,
            'risk_tier': (v) => v.toUpperCase(),
            'leverage': (v) => `${v}x`,
            'watchdog_threshold': (v) => `${(v * 100).toFixed(2)}%`,
            'rebalance_enabled': (v) => v ? 'ON' : 'OFF',
            'max_position_usd': (v) => `$${v}`,
            'take_profit_pct': (v) => `+${v}%`,
            'stop_loss_pct': (v) => `-${v}%`,
            'max_pods': (v) => v,
            'sentiment_threshold': (v) => `${(v * 100).toFixed(0)}%`
        };

        Object.entries(config).forEach(([key, value]) => {
            const el = card.querySelector(`[data-config="${key}"]`);
            if (el && formatters[key]) {
                el.textContent = formatters[key](value);
            }
        });
    }

    /**
     * Toggle engine on/off
     */
    toggleEngine(engineName) {
        const state = this.engineStates[engineName];
        const isRunning = state?.status === 'running' || state?.status === 'starting';
        const mode = this.engineModes[engineName] || 'paper';

        if (isRunning) {
            this.sendCommand('STOP_ENGINE', { engine: engineName });
            this.addLog('SYSTEM', 'INFO', `Stopping ${engineName} engine...`);
        } else {
            this.sendCommand('START_ENGINE', { engine: engineName, mode: mode });
            this.addLog('SYSTEM', 'INFO', `Starting ${engineName} engine in ${mode.toUpperCase()} mode...`);
        }
    }

    /**
     * Set engine execution mode (paper/live)
     */
    setEngineMode(engineName, mode) {
        this.engineModes[engineName] = mode;

        // Update UI buttons
        const selector = document.querySelector(`.mode-selector[data-engine="${engineName}"]`);
        if (selector) {
            selector.querySelectorAll('.mode-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.mode === mode);
            });
        }

        this.addLog('SYSTEM', 'INFO', `${engineName} mode set to ${mode.toUpperCase()}`);
    }

    /**
     * Handle engine response from server
     */
    handleEngineResponse(packet) {
        const { action, engine, result } = packet;

        if (result.success) {
            this.addLog('SYSTEM', 'SUCCESS', result.message);
        } else {
            this.addLog('SYSTEM', 'ERROR', result.message);
        }
    }

    /**
     * Open settings modal for an engine
     */
    openSettingsModal(engineName) {
        this.editingEngine = engineName;
        const state = this.engineStates[engineName];

        if (!state) {
            this.addLog('SYSTEM', 'ERROR', `Unknown engine: ${engineName}`);
            return;
        }

        // Update modal title
        document.getElementById('modal-engine-title').textContent =
            `${state.display_name || engineName} Settings`;

        // Build form
        const formContainer = document.getElementById('modal-config-form');
        formContainer.innerHTML = this.buildConfigForm(engineName, state.config);

        // Show modal
        document.getElementById('settings-modal').classList.add('active');
    }

    /**
     * Build config form HTML
     */
    buildConfigForm(engineName, config) {
        const fieldMeta = {
            'arb': {
                'min_spread': { label: 'Minimum Spread (%)', type: 'number', step: 0.1 },
                'max_trade_usd': { label: 'Max Trade Size ($)', type: 'number', step: 10 },
                'scan_interval': { label: 'Scan Interval (sec)', type: 'number', step: 1 },
                'risk_tier': { label: 'Risk Tier', type: 'select', options: ['low', 'mid', 'high', 'all'] }
            },
            'funding': {
                'leverage': { label: 'Leverage', type: 'number', step: 0.5, min: 1, max: 10 },
                'watchdog_threshold': { label: 'Watchdog Threshold', type: 'number', step: 0.0001 },
                'rebalance_enabled': { label: 'Auto Rebalance', type: 'checkbox' },
                'max_position_usd': { label: 'Max Position ($)', type: 'number', step: 50 }
            },
            'scalp': {
                'take_profit_pct': { label: 'Take Profit (%)', type: 'number', step: 1 },
                'stop_loss_pct': { label: 'Stop Loss (%)', type: 'number', step: 1 },
                'max_pods': { label: 'Max Pods', type: 'number', step: 1, min: 1, max: 10 },
                'sentiment_threshold': { label: 'Sentiment Threshold', type: 'number', step: 0.05, min: 0, max: 1 }
            }
        };

        const fields = fieldMeta[engineName] || {};

        return Object.entries(fields).map(([key, meta]) => {
            const value = config[key] ?? '';

            if (meta.type === 'checkbox') {
                return `
                    <div class="form-group">
                        <label class="form-label" style="display: flex; align-items: center; gap: 10px;">
                            <input type="checkbox" name="${key}" ${value ? 'checked' : ''}>
                            ${meta.label}
                        </label>
                    </div>
                `;
            }

            if (meta.type === 'select') {
                const options = meta.options.map(opt =>
                    `<option value="${opt}" ${value === opt ? 'selected' : ''}>${opt.toUpperCase()}</option>`
                ).join('');
                return `
                    <div class="form-group">
                        <label class="form-label">${meta.label}</label>
                        <select name="${key}" class="form-input">${options}</select>
                    </div>
                `;
            }

            return `
                <div class="form-group">
                    <label class="form-label">${meta.label}</label>
                    <input type="${meta.type}" name="${key}" value="${value}" 
                           class="form-input"
                           ${meta.step ? `step="${meta.step}"` : ''}
                           ${meta.min !== undefined ? `min="${meta.min}"` : ''}
                           ${meta.max !== undefined ? `max="${meta.max}"` : ''}>
                </div>
            `;
        }).join('');
    }

    /**
     * Save engine configuration
     */
    saveEngineConfig() {
        if (!this.editingEngine) return;

        const form = document.getElementById('modal-config-form');
        const config = {};

        form.querySelectorAll('input, select').forEach(input => {
            const name = input.name;
            if (input.type === 'checkbox') {
                config[name] = input.checked;
            } else if (input.type === 'number') {
                config[name] = parseFloat(input.value);
            } else {
                config[name] = input.value;
            }
        });

        this.sendCommand('UPDATE_CONFIG', {
            engine: this.editingEngine,
            config
        });

        this.addLog('SYSTEM', 'INFO', `Updated config for ${this.editingEngine}`);
        this.closeAllModals();
    }

    /**
     * Open SOS confirmation modal
     */
    openSOSModal() {
        document.getElementById('sos-modal').classList.add('active');
    }

    /**
     * Execute emergency stop
     */
    executeSOS() {
        this.sendCommand('SOS');
        this.addLog('SYSTEM', 'WARNING', '🆘 EMERGENCY STOP INITIATED');
        this.closeAllModals();
    }

    /**
     * Handle SOS response
     */
    handleSOSResponse(packet) {
        const { result } = packet;
        if (result.success) {
            this.addLog('SYSTEM', 'WARNING', `SOS Complete: ${result.engines_stopped} engines stopped`);
        } else {
            this.addLog('SYSTEM', 'ERROR', `SOS Failed: ${result.message}`);
        }
    }

    /**
     * Close all modals
     */
    closeAllModals() {
        document.querySelectorAll('.modal-overlay').forEach(modal => {
            modal.classList.remove('active');
        });
        this.editingEngine = null;
    }

    /**
     * Update layout based on mode
     */
    updateLayoutForMode(mode) {
        const intelTitle = document.getElementById('intel-title');
        const intelHeader = document.getElementById('intel-header');

        if (mode === 'SCALP') {
            intelTitle.textContent = 'Snipe Intelligence (Pods)';
            intelHeader.innerHTML = `
                <th>TOKEN</th>
                <th>SIGNAL</th>
                <th>ACTION</th>
                <th>CONF</th>
            `;
        } else {
            intelTitle.textContent = 'Arb Opportunities';
            intelHeader.innerHTML = `
                <th>TOKEN</th>
                <th>ROUTE</th>
                <th>SPREAD</th>
                <th>EST PROFIT</th>
            `;
        }
    }

    /**
     * Update intelligence table
     */
    updateIntelTable(mode, item) {
        if (this.intelTableBody.innerText.includes('Listening')) {
            this.intelTableBody.innerHTML = '';
        }

        const row = document.createElement('tr');

        if (mode === 'ARB') {
            const profitColor = item.profit_pct > 0 ? 'var(--neon-green)' : 'white';
            row.innerHTML = `
                <td>${item.token}</td>
                <td style="font-size: 0.7rem; color: var(--text-dim);">${item.route}</td>
                <td style="color: ${profitColor}">${item.profit_pct.toFixed(2)}%</td>
                <td>$${item.est_profit_sol.toFixed(2)}</td>
            `;
        } else if (mode === 'SCALP') {
            const actionColor = item.action === 'BUY' ? 'var(--neon-green)' : 'var(--neon-red)';
            row.innerHTML = `
                <td>${item.token}</td>
                <td>${item.signal}</td>
                <td style="color: ${actionColor}; font-weight: bold;">${item.action}</td>
                <td>${(item.confidence * 100).toFixed(0)}%</td>
            `;
        }

        this.intelTableBody.prepend(row);

        if (this.intelTableBody.children.length > 15) {
            this.intelTableBody.removeChild(this.intelTableBody.lastChild);
        }
    }

    /**
     * Update inventory table
     */
    updateInventory(items) {
        this.inventoryTableBody.innerHTML = '';
        items.forEach(item => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${item.symbol}</td>
                <td style="text-align: right;">${item.amount.toFixed(3)}</td>
                <td style="text-align: right;">$${item.value_usd.toFixed(2)}</td>
            `;
            this.inventoryTableBody.appendChild(row);
        });
    }

    /**
     * Add log entry
     */
    addLog(source, level, message, timestamp) {
        const time = timestamp
            ? new Date(timestamp * 1000).toLocaleTimeString()
            : new Date().toLocaleTimeString();

        const entry = document.createElement('div');
        entry.className = `log-entry ${level}`;
        entry.innerHTML = `<span style="color: var(--text-dim); font-size: 0.7rem;">[${time}]</span> <span style="font-weight: bold;">[${source}]</span> ${message}`;

        this.logStream.prepend(entry);

        if (this.logStream.children.length > this.maxLogs) {
            this.logStream.removeChild(this.logStream.lastChild);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // SCANNER VIEW METHODS
    // ═══════════════════════════════════════════════════════════════

    /**
     * Update scanner view with aggregated data
     */
    updateScanner(data) {
        const statusEl = document.getElementById('scanner-status');
        if (statusEl) {
            const activeCount = data.total_active || 0;
            statusEl.textContent = `${activeCount} active signals`;
        }

        // Update critical alerts
        this.updateCriticalAlerts(data.critical_alerts || []);

        // Update opportunity heatmap
        this.updateOpportunitiesHeatmap(data.top_opportunities || []);

        // Update source breakdown
        if (data.by_source) {
            this.updateSourceCard('arb', data.by_source.arb);
            this.updateSourceCard('funding', data.by_source.funding);
            this.updateSourceCard('scalp', data.by_source.scalp);
        }
    }

    /**
     * Add individual signal to scanner (real-time)
     */
    addToScanner(source, data) {
        // Convert to scanner format and add to display
        const signal = this.convertToScannerSignal(source, data);
        if (!signal) return;

        // Add to opportunities heatmap if significant
        if (signal.urgency >= 1) {
            const heatmap = document.getElementById('opportunities-heatmap');
            if (heatmap) {
                // Remove placeholder
                const placeholder = heatmap.querySelector('.opportunity-placeholder');
                if (placeholder) placeholder.remove();

                // Add new card at start
                const card = this.renderOpportunityCard(signal);
                heatmap.insertAdjacentHTML('afterbegin', card);

                // Limit to 10 cards
                while (heatmap.children.length > 10) {
                    heatmap.removeChild(heatmap.lastChild);
                }
            }
        }

        // Update source card
        this.addSignalToSource(source, signal);
    }

    /**
     * Convert raw signal data to scanner format
     */
    convertToScannerSignal(source, data) {
        if (source === 'arb') {
            const profitPct = data.profit_pct || 0;
            return {
                symbol: data.token || '???',
                source: 'arb',
                value: profitPct,
                valueDisplay: `+${profitPct.toFixed(2)}%`,
                urgency: profitPct > 2 ? 3 : profitPct > 1 ? 2 : profitPct > 0.5 ? 1 : 0,
                reason: data.route || '',
                timestamp: Date.now()
            };
        } else if (source === 'scalp') {
            const confidence = data.confidence || 0;
            return {
                symbol: data.token || '???',
                source: 'scalp',
                value: confidence * 100,
                valueDisplay: `${(confidence * 100).toFixed(0)}%`,
                urgency: confidence > 0.9 ? 2 : confidence > 0.7 ? 1 : 0,
                reason: data.signal || data.action || '',
                direction: data.action === 'BUY' ? 'long' : 'short',
                timestamp: Date.now()
            };
        }
        return null;
    }

    /**
     * Update critical alerts banner
     */
    updateCriticalAlerts(alerts) {
        const container = document.getElementById('critical-alerts');
        const list = document.getElementById('critical-alerts-list');

        if (!container || !list) return;

        if (alerts.length === 0) {
            container.style.display = 'none';
            return;
        }

        container.style.display = 'block';
        list.innerHTML = alerts.map(alert => `
            <div class="signal-item" style="border-left: 2px solid var(--neon-red);">
                <div class="signal-info">
                    <span class="signal-symbol">${alert.symbol}</span>
                    <span class="signal-reason">${alert.reason}</span>
                </div>
                <span class="signal-value negative">${this.formatValue(alert.value, alert.source)}</span>
            </div>
        `).join('');
    }

    /**
     * Update opportunities heatmap
     */
    updateOpportunitiesHeatmap(opportunities) {
        const container = document.getElementById('opportunities-heatmap');
        if (!container) return;

        if (opportunities.length === 0) {
            container.innerHTML = '<div class="opportunity-placeholder">Scanning for opportunities...</div>';
            return;
        }

        container.innerHTML = opportunities.map(opp => this.renderOpportunityCard(opp)).join('');
    }

    /**
     * Render single opportunity card
     */
    renderOpportunityCard(opp) {
        const urgencyClass = `urgency-${opp.urgency}`;
        const valueClass = opp.value < 0 ? 'negative' : '';
        const sourceColors = {
            'arb': 'var(--neon-green)',
            'funding': 'var(--neon-blue)',
            'scalp': 'var(--neon-gold)'
        };

        return `
            <div class="opportunity-card ${urgencyClass}">
                <div class="opp-header">
                    <span class="opp-symbol">${opp.symbol}</span>
                    <span class="opp-source" style="color: ${sourceColors[opp.source] || 'white'}">
                        ${opp.source}
                    </span>
                </div>
                <div class="opp-value ${valueClass}">
                    ${opp.valueDisplay || this.formatValue(opp.value, opp.source)}
                </div>
                <div class="opp-meta">${opp.reason || ''}</div>
            </div>
        `;
    }

    /**
     * Update source breakdown card
     */
    updateSourceCard(source, data) {
        if (!data) return;

        const countEl = document.getElementById(`${source}-count`);
        const signalsEl = document.getElementById(`${source}-signals`);

        if (countEl) {
            countEl.textContent = data.count || 0;
        }

        if (signalsEl && data.signals) {
            if (data.signals.length === 0) {
                signalsEl.innerHTML = `<div class="signal-placeholder">No ${source} signals</div>`;
            } else {
                signalsEl.innerHTML = data.signals.map(s => this.renderSignalItem(s)).join('');
            }
        }
    }

    /**
     * Add signal to source card (real-time)
     */
    addSignalToSource(source, signal) {
        const signalsEl = document.getElementById(`${source}-signals`);
        const countEl = document.getElementById(`${source}-count`);

        if (!signalsEl) return;

        // Remove placeholder
        const placeholder = signalsEl.querySelector('.signal-placeholder');
        if (placeholder) placeholder.remove();

        // Add new signal
        signalsEl.insertAdjacentHTML('afterbegin', this.renderSignalItem(signal));

        // Limit to 5 signals
        while (signalsEl.children.length > 5) {
            signalsEl.removeChild(signalsEl.lastChild);
        }

        // Update count
        if (countEl) {
            countEl.textContent = parseInt(countEl.textContent || 0) + 1;
        }
    }

    /**
     * Render signal item for source card
     */
    renderSignalItem(signal) {
        const valueClass = signal.value < 0 ? 'negative' : 'positive';
        return `
            <div class="signal-item">
                <div class="signal-info">
                    <span class="signal-symbol">${signal.symbol}</span>
                    <span class="signal-reason">${signal.reason || ''}</span>
                </div>
                <span class="signal-value ${valueClass}">
                    ${signal.valueDisplay || this.formatValue(signal.value, signal.source)}
                </span>
            </div>
        `;
    }

    /**
     * Format value based on source type
     */
    formatValue(value, source) {
        if (source === 'arb') return `+${value.toFixed(2)}%`;
        if (source === 'funding') return `${(value).toFixed(3)}%`;
        if (source === 'scalp') return `${value.toFixed(0)}%`;
        return `${value}`;
    }
}

// ═══════════════════════════════════════════════════════════════
// GLOBAL INIT
// ═══════════════════════════════════════════════════════════════

window.addEventListener('load', () => {
    window.app = new DashboardApp();
});
