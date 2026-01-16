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

            case 'COMMAND_RESULT':
                // Task 3.5 & 4.4: Handle position command responses
                // Requirements: 8.8, 8.9
                this.handleCommandResult(data);
                break;

            case 'FUNDING_UPDATE':
                // Task 5.1: Handle real-time funding engine updates
                // Requirements: 1.7, 2.9, 4.12
                this.handleFundingUpdate(data);
                break;

            case 'HEALTH_ALERT':
                // Task 5.6: Handle health warnings
                // Requirements: 2.4, 2.5
                this.handleHealthAlert(data);
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

    // ═══════════════════════════════════════════════════════════════
    // FUNDING ENGINE METHODS (Phase 2: Market Data Display)
    // ═══════════════════════════════════════════════════════════════

    /**
     * Fetch Funding market opportunities
     * Task 2.1: Implement fetchFundingMarkets() method
     * Requirements: 2.1, 2.8
     */
    async fetchFundingMarkets() {
        try {
            const response = await fetch('/api/drift/markets');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            // Render market data
            this.renderFundingTable(data.markets);
            this.renderOpportunityCards(data.markets);
            this.updateMarketStats(data.stats);
            
            // Update last refresh timestamp
            const timestampEl = document.getElementById('funding-last-refresh');
            if (timestampEl) {
                timestampEl.textContent = new Date().toLocaleTimeString();
            }
            
        } catch (error) {
            console.error('[FUNDING] Failed to fetch markets:', error);
            this.showFundingError('Failed to load market data. Please try again.');
        }
    }

    /**
     * Render funding rates table
     * Task 2.2: Implement renderFundingTable(markets) method
     * Requirements: 2.2
     */
    renderFundingTable(markets) {
        const tbody = document.getElementById('funding-funding-body');
        if (!tbody) return;
        
        if (!markets || markets.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No markets available</td></tr>';
            return;
        }
        
        // Sort by APR (highest first)
        const sorted = [...markets].sort((a, b) => Math.abs(b.apr) - Math.abs(a.apr));
        
        tbody.innerHTML = sorted.map(m => {
            const rateColor = m.rate >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
            const aprColor = m.apr >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
            const rate1h = (m.rate / 8).toFixed(4);
            const rate8h = m.rate.toFixed(4);
            
            return `
                <tr>
                    <td style="font-weight: bold;">${m.symbol}</td>
                    <td style="color: ${rateColor}; text-align: right;">${rate1h}%</td>
                    <td style="color: ${rateColor}; text-align: right;">${rate8h}%</td>
                    <td style="color: ${aprColor}; font-weight: bold; text-align: right;">
                        ${m.apr >= 0 ? '+' : ''}${m.apr.toFixed(2)}%
                    </td>
                    <td style="text-transform: uppercase; font-size: 0.75rem;">
                        ${m.direction}
                    </td>
                    <td style="text-align: right;">${this.formatNumber(m.oi)}</td>
                    <td>
                        <button class="btn-xs funding-take-btn" 
                                data-market="${m.symbol}" 
                                data-direction="${m.direction}"
                                data-apr="${m.apr}">
                            Take
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
        
        // Bind click handlers to "Take" buttons
        tbody.querySelectorAll('.funding-take-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const market = btn.dataset.market;
                const direction = btn.dataset.direction;
                const apr = parseFloat(btn.dataset.apr);
                this.handleTakePosition(market, direction, apr);
            });
        });
    }

    /**
     * Render opportunity cards (top 3)
     * Task 2.3: Implement renderOpportunityCards(opportunities) method
     * Requirements: 2.2
     */
    renderOpportunityCards(markets) {
        const container = document.getElementById('drift-opportunities');
        if (!container) return;
        
        if (!markets || markets.length === 0) {
            container.innerHTML = '<div class="empty-state">No opportunities found</div>';
            return;
        }
        
        // Get top 3 by absolute APR
        const top3 = [...markets]
            .sort((a, b) => Math.abs(b.apr) - Math.abs(a.apr))
            .slice(0, 3);
        
        container.innerHTML = top3.map(m => {
            const bgColor = m.apr >= 0 ? 'rgba(0,255,136,0.05)' : 'rgba(255,60,60,0.05)';
            const borderColor = m.apr >= 0 ? 'rgba(0,255,136,0.2)' : 'rgba(255,60,60,0.2)';
            const aprColor = m.apr >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
            const directionText = m.direction === 'shorts' ? 'SHORT' : 'LONG';
            
            return `
                <div class="opportunity-card" 
                     style="background: ${bgColor}; border: 1px solid ${borderColor}; border-radius: 8px; padding: 10px; margin: 5px 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span class="opp-symbol" style="font-weight: bold; font-size: 1.1rem;">${m.symbol}</span>
                            <span class="opp-direction" style="color: ${aprColor}; margin-left: 8px; font-size: 0.8rem;">
                                ${directionText}
                            </span>
                        </div>
                        <div style="text-align: right;">
                            <div class="opp-apr" style="color: ${aprColor}; font-weight: bold;">
                                ${m.apr >= 0 ? '+' : ''}${m.apr.toFixed(1)}% APR
                            </div>
                            <div style="font-size: 0.7rem; color: var(--text-dim);">
                                Funding pays ${m.direction}
                            </div>
                        </div>
                    </div>
                    <button class="btn-xs drift-take-btn" 
                            data-market="${m.symbol}" 
                            data-direction="${m.direction}"
                            data-apr="${m.apr}"
                            style="width: 100%; margin-top: 8px;">
                        Take Position
                    </button>
                </div>
            `;
        }).join('');
        
        // Bind click handlers
        container.querySelectorAll('.drift-take-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const market = btn.dataset.market;
                const direction = btn.dataset.direction;
                const apr = parseFloat(btn.dataset.apr);
                this.handleTakePosition(market, direction, apr);
            });
        });
    }

    /**
     * Update market statistics display
     * Task 2.4: Implement updateMarketStats(stats) method
     * Requirements: 2.2
     */
    updateMarketStats(stats) {
        const oiEl = document.getElementById('drift-total-oi');
        const volumeEl = document.getElementById('drift-24h-volume');
        const fundingEl = document.getElementById('drift-avg-funding');
        
        if (oiEl) oiEl.textContent = this.formatNumber(stats.total_oi);
        if (volumeEl) volumeEl.textContent = this.formatNumber(stats.volume_24h);
        if (fundingEl) {
            const sign = stats.avg_funding >= 0 ? '+' : '';
            fundingEl.textContent = `${sign}${stats.avg_funding.toFixed(2)}%`;
        }
    }

    /**
     * Format large numbers with K/M/B suffixes
     */
    formatNumber(num) {
        if (num >= 1e9) return `$${(num / 1e9).toFixed(2)}B`;
        if (num >= 1e6) return `$${(num / 1e6).toFixed(2)}M`;
        if (num >= 1e3) return `$${(num / 1e3).toFixed(2)}K`;
        return `$${num.toFixed(2)}`;
    }

    /**
     * Show error message in Drift UI
     */
    showDriftError(message) {
        const tbody = document.getElementById('drift-funding-body');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="empty-state" style="color: var(--neon-red);">
                        ⚠️ ${message}
                        <button class="btn-xs" onclick="app.fetchDriftMarkets()" style="margin-left: 10px;">
                            Retry
                        </button>
                    </td>
                </tr>
            `;
        }
    }

    /**
     * Handle "Take Position" button click
     * Task 3.2: Implement handleTakePosition(market, direction) method
     * Requirements: 4.1
     */
    handleTakePosition(market, direction, apr) {
        console.log('[DRIFT] Take position:', market, direction, apr);
        this.addLog('DRIFT', 'INFO', `Opening position modal for ${market} (${direction})`);
        
        // Store current position data
        this.currentPositionData = {
            market,
            direction,
            apr
        };
        
        // Get current engine state for available collateral
        const fundingState = this.engineStates['funding'] || {};
        const availableCollateral = fundingState.free_collateral || 0;
        const solPrice = fundingState.sol_price || 150;
        const availableSol = availableCollateral / solPrice;
        
        // Populate modal
        document.getElementById('drift-modal-market').textContent = market;
        document.getElementById('drift-modal-direction').textContent = direction.toUpperCase();
        document.getElementById('drift-modal-apr').textContent = `${apr >= 0 ? '+' : ''}${apr.toFixed(2)}%`;
        document.getElementById('drift-modal-available').textContent = availableSol.toFixed(3);
        
        // Reset input
        const sizeInput = document.getElementById('drift-position-size');
        sizeInput.value = '';
        sizeInput.max = availableSol.toFixed(3);
        
        // Reset leverage preview
        document.getElementById('drift-modal-leverage').textContent = '0.0x';
        document.getElementById('drift-modal-cost').textContent = '$0.00';
        document.getElementById('drift-modal-health-after').textContent = '100%';
        
        // Hide warning
        document.getElementById('drift-modal-warning').style.display = 'none';
        
        // Bind input change handler for live preview
        sizeInput.oninput = () => this.updatePositionPreview();
        
        // Show modal
        document.getElementById('drift-position-modal').style.display = 'flex';
    }
    
    /**
     * Update position preview as user types size
     * Task 3.3: Implement confirmTakePosition() method (preview part)
     * Requirements: 4.2, 6.7
     */
    updatePositionPreview() {
        const sizeInput = document.getElementById('drift-position-size');
        const size = parseFloat(sizeInput.value) || 0;
        
        // Get current state
        const fundingState = this.engineStates['funding'] || {};
        const solPrice = fundingState.sol_price || 150;
        const currentEquity = fundingState.equity || 1000;
        const currentLeverage = fundingState.leverage || 0;
        const currentHealth = fundingState.health || 100;
        
        // Calculate new metrics
        const positionValue = size * solPrice;
        const newLeverage = ((currentLeverage * currentEquity) + positionValue) / currentEquity;
        const estimatedCost = positionValue * 0.001; // 0.1% fee estimate
        
        // Estimate health after (simplified)
        const marginRequired = positionValue * 0.05; // 5% maintenance margin
        const healthAfter = Math.max(0, Math.min(100, ((currentEquity - estimatedCost) / (marginRequired + (currentEquity * currentLeverage * 0.05))) * 100));
        
        // Update preview
        document.getElementById('drift-modal-leverage').textContent = `${newLeverage.toFixed(2)}x`;
        document.getElementById('drift-modal-cost').textContent = `$${estimatedCost.toFixed(2)}`;
        document.getElementById('drift-modal-health-after').textContent = `${healthAfter.toFixed(1)}%`;
        
        // Show warnings
        const warningEl = document.getElementById('drift-modal-warning');
        const warningText = document.getElementById('drift-modal-warning-text');
        const confirmBtn = document.getElementById('drift-modal-confirm-btn');
        
        if (size < 0.005) {
            warningEl.style.display = 'block';
            warningText.textContent = 'Minimum position size is 0.005 SOL';
            confirmBtn.disabled = true;
        } else if (newLeverage > 5.0) {
            warningEl.style.display = 'block';
            warningText.textContent = `Leverage ${newLeverage.toFixed(2)}x exceeds maximum 5.0x`;
            confirmBtn.disabled = true;
        } else if (healthAfter < 60) {
            warningEl.style.display = 'block';
            warningText.textContent = `Health would drop to ${healthAfter.toFixed(1)}% (minimum 60%)`;
            confirmBtn.disabled = true;
        } else {
            warningEl.style.display = 'none';
            confirmBtn.disabled = false;
        }
    }
    
    /**
     * Confirm and execute position
     * Task 3.4: Send DRIFT_OPEN_POSITION command
     * Requirements: 4.3, 8.6
     */
    confirmPosition() {
        const size = parseFloat(document.getElementById('drift-position-size').value);
        
        if (!size || size < 0.005) {
            alert('Please enter a valid position size (min 0.005 SOL)');
            return;
        }
        
        const { market, direction } = this.currentPositionData;
        
        // Show loading state
        const confirmBtn = document.getElementById('drift-modal-confirm-btn');
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Opening...';
        
        // Send WebSocket command
        // Task 3.4: Send DRIFT_OPEN_POSITION command
        this.sendCommand('DRIFT_OPEN_POSITION', {
            market,
            direction,
            size
        });
        
        this.addLog('DRIFT', 'INFO', `Opening ${direction} position: ${size} ${market}`);
    }
    
    /**
     * Handle "Leave Position" button click
     * Task 4.2: Implement handleLeavePosition(market) method
     * Requirements: 4.8
     */
    handleLeavePosition(market) {
        console.log('[DRIFT] Leave position:', market);
        this.addLog('DRIFT', 'INFO', `Opening close modal for ${market}`);
        
        // Find position in current state
        const fundingState = this.engineStates['funding'] || {};
        const positions = fundingState.positions || [];
        const position = positions.find(p => p.market === market);
        
        if (!position) {
            alert('Position not found');
            return;
        }
        
        // Store current position
        this.currentClosePosition = position;
        
        // Populate modal
        document.getElementById('drift-close-modal-market').textContent = position.market;
        document.getElementById('drift-close-modal-side').textContent = position.amount < 0 ? 'SHORT' : 'LONG';
        document.getElementById('drift-close-modal-size').textContent = `${Math.abs(position.amount).toFixed(3)} SOL`;
        document.getElementById('drift-close-modal-entry').textContent = `$${position.entry_price.toFixed(2)}`;
        document.getElementById('drift-close-modal-mark').textContent = `$${position.mark_price.toFixed(2)}`;
        
        // PnL color
        const pnlEl = document.getElementById('drift-close-modal-pnl');
        const pnl = position.unrealized_pnl || 0;
        pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
        pnlEl.style.color = pnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
        
        // Expected proceeds
        const proceeds = Math.abs(position.amount) * position.mark_price;
        document.getElementById('drift-close-modal-proceeds').textContent = `$${proceeds.toFixed(2)}`;
        
        // Show modal
        document.getElementById('drift-close-modal').style.display = 'flex';
    }
    
    /**
     * Confirm and execute position close
     * Task 4.3: Implement confirmLeavePosition() method
     * Requirements: 4.9, 8.7
     */
    confirmClose() {
        if (!this.currentClosePosition) {
            alert('No position selected');
            return;
        }
        
        const market = this.currentClosePosition.market;
        
        // Show loading state
        const confirmBtn = document.getElementById('drift-close-modal-confirm-btn');
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Closing...';
        
        // Send WebSocket command
        // Task 4.3: Send DRIFT_CLOSE_POSITION command
        this.sendCommand('DRIFT_CLOSE_POSITION', {
            market
        });
        
        this.addLog('DRIFT', 'INFO', `Closing position: ${market}`);
    }
    
    /**
     * Close position modal
     */
    closeModal() {
        document.getElementById('drift-position-modal').style.display = 'none';
        
        // Reset button state
        const confirmBtn = document.getElementById('drift-modal-confirm-btn');
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = '<i class="fa-solid fa-check"></i> Confirm Position';
    }
    
    /**
     * Close close-position modal
     */
    closeCloseModal() {
        document.getElementById('drift-close-modal').style.display = 'none';
        
        // Reset button state
        const confirmBtn = document.getElementById('drift-close-modal-confirm-btn');
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = '<i class="fa-solid fa-times-circle"></i> Close Position';
    }
    
    /**
     * Handle COMMAND_RESULT from WebSocket
     * Task 3.5 & 4.4: Handle position command responses
     * Requirements: 8.8, 8.9
     */
    handleCommandResult(data) {
        const { action, success, message, tx_signature } = data;
        
        if (action === 'DRIFT_OPEN_POSITION') {
            if (success) {
                this.addLog('DRIFT', 'SUCCESS', `Position opened: ${message}`);
                if (tx_signature) {
                    this.addLog('DRIFT', 'INFO', `TX: ${tx_signature}`);
                }
                this.closeModal();
                // Show success toast
                this.showToast('success', 'Position Opened', message);
            } else {
                this.addLog('DRIFT', 'ERROR', `Failed to open position: ${message}`);
                // Re-enable button
                const confirmBtn = document.getElementById('drift-modal-confirm-btn');
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = '<i class="fa-solid fa-check"></i> Confirm Position';
                // Show error toast
                this.showToast('error', 'Position Failed', message);
            }
        } else if (action === 'DRIFT_CLOSE_POSITION') {
            if (success) {
                this.addLog('DRIFT', 'SUCCESS', `Position closed: ${message}`);
                this.closeCloseModal();
                // Show success toast
                this.showToast('success', 'Position Closed', message);
            } else {
                this.addLog('DRIFT', 'ERROR', `Failed to close position: ${message}`);
                // Re-enable button
                const confirmBtn = document.getElementById('drift-close-modal-confirm-btn');
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = '<i class="fa-solid fa-times-circle"></i> Close Position';
                // Show error toast
                this.showToast('error', 'Close Failed', message);
            }
        }
    }
    
    /**
     * Show toast notification
     */
    showToast(type, title, message) {
        // Simple toast implementation (can be enhanced with a toast library)
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'success' ? 'rgba(0,255,136,0.2)' : 'rgba(255,60,60,0.2)'};
            border: 1px solid ${type === 'success' ? 'var(--neon-green)' : 'var(--neon-red)'};
            border-radius: 8px;
            padding: 15px 20px;
            color: white;
            z-index: 10000;
            min-width: 300px;
            animation: slideIn 0.3s ease-out;
        `;
        toast.innerHTML = `
            <div style="font-weight: bold; margin-bottom: 5px;">${title}</div>
            <div style="font-size: 0.9rem; opacity: 0.9;">${message}</div>
        `;
        document.body.appendChild(toast);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }
    
    // ═══════════════════════════════════════════════════════════════
    // PHASE 5: WEBSOCKET REAL-TIME UPDATES
    // ═══════════════════════════════════════════════════════════════
    
    /**
     * Handle FUNDING_UPDATE from WebSocket
     * Task 5.1: Implement handleFundingUpdate(data) method
     * Requirements: 1.7, 2.9, 4.12
     */
    handleFundingUpdate(data) {
        const { payload } = data;
        
        if (!payload) return;
        
        // Store in engine states for other methods to access
        this.engineStates['funding'] = payload;
        
        // Update all UI components
        this.updateHealthGauge(payload.health || 100);
        this.updateLeverageMeter(payload.leverage || 0);
        this.updateDeltaDisplay(payload.net_delta || 0, payload.drift_pct || 0);
        this.updatePositionsTable(payload.positions || []);
        this.updateCollateralMetrics(payload);
    }
    
    /**
     * Update health gauge with animation
     * Task 5.2: Update health gauge animation
     * Requirements: 2.4, 2.5
     */
    updateHealthGauge(health) {
        // Clamp health to [0, 100]
        health = Math.max(0, Math.min(100, health));
        
        // Calculate needle rotation (-90° to +90°)
        // 0% = -90° (left), 50% = 0° (center), 100% = +90° (right)
        const angle = (health - 50) * 1.8; // Map 0-100 to -90 to +90
        
        // Update needle rotation
        const needle = document.getElementById('health-needle');
        if (needle) {
            needle.style.transition = 'transform 0.5s ease-out';
            needle.setAttribute('transform', `rotate(${angle}, 100, 100)`);
        }
        
        // Update percentage text
        const pctEl = document.getElementById('drift-health-pct');
        if (pctEl) {
            pctEl.textContent = `${health.toFixed(1)}%`;
        }
        
        // Update health label and color
        const labelEl = document.querySelector('.health-label');
        if (labelEl) {
            if (health >= 70) {
                labelEl.textContent = 'HEALTHY';
                labelEl.style.color = 'var(--neon-green)';
            } else if (health >= 50) {
                labelEl.textContent = 'MODERATE';
                labelEl.style.color = 'var(--neon-yellow)';
            } else if (health >= 20) {
                labelEl.textContent = 'WARNING';
                labelEl.style.color = 'var(--neon-orange)';
            } else {
                labelEl.textContent = 'CRITICAL';
                labelEl.style.color = 'var(--neon-red)';
            }
        }
    }
    
    /**
     * Update leverage meter with animation
     * Task 5.3: Update leverage meter
     * Requirements: 4.2, 6.7
     */
    updateLeverageMeter(leverage) {
        // Calculate fill percentage (0-20x scale)
        const maxLeverage = 20;
        const fillPct = Math.min(100, (leverage / maxLeverage) * 100);
        
        // Update bar fill
        const fillEl = document.getElementById('drift-leverage-fill');
        if (fillEl) {
            fillEl.style.transition = 'width 0.5s ease-out, background-color 0.5s ease-out';
            fillEl.style.width = `${fillPct}%`;
            
            // Color based on leverage
            if (leverage < 3) {
                fillEl.style.background = 'linear-gradient(90deg, var(--neon-green), var(--neon-cyan))';
            } else if (leverage < 5) {
                fillEl.style.background = 'linear-gradient(90deg, var(--neon-yellow), var(--neon-orange))';
            } else {
                fillEl.style.background = 'linear-gradient(90deg, var(--neon-orange), var(--neon-red))';
            }
        }
        
        // Update leverage text
        const leverageEl = document.getElementById('drift-current-leverage');
        if (leverageEl) {
            leverageEl.textContent = `${leverage.toFixed(2)}x`;
            
            // Color based on leverage
            if (leverage < 3) {
                leverageEl.style.color = 'var(--neon-green)';
            } else if (leverage < 5) {
                leverageEl.style.color = 'var(--neon-yellow)';
            } else {
                leverageEl.style.color = 'var(--neon-red)';
            }
        }
    }
    
    /**
     * Update delta display
     * Task 5.4: Update delta display
     * Requirements: 5.1, 5.2
     */
    updateDeltaDisplay(netDelta, driftPct) {
        // Update delta value
        const valueEl = document.getElementById('drift-delta-value');
        if (valueEl) {
            valueEl.textContent = netDelta.toFixed(3);
        }
        
        // Update delta status
        const statusEl = document.getElementById('drift-delta-status');
        if (statusEl) {
            // Remove all status classes
            statusEl.classList.remove('neutral', 'long-bias', 'short-bias');
            
            if (Math.abs(driftPct) < 1.0) {
                statusEl.textContent = 'NEUTRAL';
                statusEl.classList.add('neutral');
                statusEl.style.color = 'var(--neon-green)';
            } else if (driftPct > 0) {
                statusEl.textContent = 'LONG BIAS';
                statusEl.classList.add('long-bias');
                statusEl.style.color = 'var(--neon-cyan)';
            } else {
                statusEl.textContent = 'SHORT BIAS';
                statusEl.classList.add('short-bias');
                statusEl.style.color = 'var(--neon-purple)';
            }
        }
    }
    
    /**
     * Update positions table
     * Task 5.5: Update positions table
     * Requirements: 4.12
     */
    updatePositionsTable(positions) {
        const tbody = document.getElementById('drift-positions-body');
        if (!tbody) return;
        
        // Clear existing rows
        tbody.innerHTML = '';
        
        if (!positions || positions.length === 0) {
            tbody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="8" class="empty-state">No open positions</td>
                </tr>
            `;
            return;
        }
        
        // Render position rows
        positions.forEach(pos => {
            const side = pos.amount < 0 ? 'SHORT' : 'LONG';
            const sideColor = pos.amount < 0 ? 'var(--neon-purple)' : 'var(--neon-cyan)';
            const pnlColor = pos.unrealized_pnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td style="font-weight: bold;">${pos.market}</td>
                <td style="color: ${sideColor};">${side}</td>
                <td>${Math.abs(pos.amount).toFixed(3)}</td>
                <td>$${pos.entry_price.toFixed(2)}</td>
                <td>$${pos.mark_price.toFixed(2)}</td>
                <td style="color: ${pnlColor}; font-weight: bold;">
                    ${pos.unrealized_pnl >= 0 ? '+' : ''}$${pos.unrealized_pnl.toFixed(2)}
                </td>
                <td>${pos.liq_price > 0 ? '$' + pos.liq_price.toFixed(2) : 'N/A'}</td>
                <td>
                    <button class="btn-xs btn-danger drift-leave-btn" 
                            data-market="${pos.market}">
                        Leave
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
        
        // Bind click handlers to "Leave" buttons
        tbody.querySelectorAll('.drift-leave-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const market = btn.dataset.market;
                this.handleLeavePosition(market);
            });
        });
    }
    
    /**
     * Update collateral metrics
     * Task 5.1: Update collateral metrics (part of handleFundingUpdate)
     * Requirements: 1.7
     */
    updateCollateralMetrics(payload) {
        // Total Collateral
        const totalCollateralEl = document.getElementById('drift-total-collateral');
        if (totalCollateralEl && payload.total_collateral !== undefined) {
            totalCollateralEl.textContent = `$${payload.total_collateral.toFixed(2)}`;
        }
        
        // Free Collateral
        const freeCollateralEl = document.getElementById('drift-free-collateral');
        if (freeCollateralEl && payload.free_collateral !== undefined) {
            freeCollateralEl.textContent = `$${payload.free_collateral.toFixed(2)}`;
        }
        
        // Maintenance Margin
        const maintMarginEl = document.getElementById('drift-maint-margin');
        if (maintMarginEl && payload.maintenance_margin !== undefined) {
            maintMarginEl.textContent = `$${payload.maintenance_margin.toFixed(2)}`;
        }
    }
    
    /**
     * Handle HEALTH_ALERT from WebSocket
     * Task 5.6: Implement handleHealthAlert(data) method
     * Requirements: 2.4, 2.5
     */
    handleHealthAlert(data) {
        const { level, health, message } = data;
        
        // Create alert banner
        const alertBanner = document.createElement('div');
        alertBanner.className = `health-alert health-alert-${level.toLowerCase()}`;
        alertBanner.style.cssText = `
            position: fixed;
            top: 70px;
            left: 50%;
            transform: translateX(-50%);
            background: ${level === 'CRITICAL' ? 'rgba(255,60,60,0.3)' : 'rgba(255,200,60,0.3)'};
            border: 2px solid ${level === 'CRITICAL' ? 'var(--neon-red)' : 'var(--neon-orange)'};
            border-radius: 8px;
            padding: 15px 25px;
            color: white;
            z-index: 9999;
            min-width: 400px;
            max-width: 600px;
            animation: slideDown 0.3s ease-out;
            display: flex;
            justify-content: space-between;
            align-items: center;
        `;
        
        alertBanner.innerHTML = `
            <div>
                <div style="font-weight: bold; font-size: 1.1rem; margin-bottom: 5px;">
                    ${level === 'CRITICAL' ? '🚨' : '⚠️'} ${level} HEALTH ALERT
                </div>
                <div style="font-size: 0.9rem;">
                    Health: ${health.toFixed(1)}% - ${message}
                </div>
            </div>
            <button onclick="this.parentElement.remove()" 
                    style="background: none; border: none; color: white; font-size: 1.5rem; cursor: pointer; padding: 0 10px;">
                ×
            </button>
        `;
        
        document.body.appendChild(alertBanner);
        
        // Auto-dismiss after 10 seconds
        setTimeout(() => {
            if (alertBanner.parentElement) {
                alertBanner.style.animation = 'slideUp 0.3s ease-in';
                setTimeout(() => alertBanner.remove(), 300);
            }
        }, 10000);
        
        // Log to console
        this.addLog('DRIFT', level === 'CRITICAL' ? 'ERROR' : 'WARNING', message);
    }
}

// ═══════════════════════════════════════════════════════════════
// GLOBAL FUNCTIONS (for onclick handlers in HTML)
// ═══════════════════════════════════════════════════════════════

window.driftCloseModal = () => window.app.closeModal();
window.driftConfirmPosition = () => window.app.confirmPosition();
window.driftCloseCloseModal = () => window.app.closeCloseModal();
window.driftConfirmClose = () => window.app.confirmClose();

// ═══════════════════════════════════════════════════════════════
// GLOBAL INIT
// ═══════════════════════════════════════════════════════════════

window.addEventListener('load', () => {
    window.app = new DashboardApp();
    
    // Bind Drift refresh button
    const refreshBtn = document.getElementById('drift-refresh-markets-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            window.app.fetchDriftMarkets();
        });
    }
    
    // Initial fetch on page load
    setTimeout(() => {
        window.app.fetchDriftMarkets();
    }, 1000);
    
    // Auto-fetch Drift markets every 30 seconds if on Drift view
    // Task 2.5: Add auto-refresh logic
    setInterval(() => {
        const driftView = document.querySelector('.engine-layout.drift-theme');
        if (driftView && driftView.offsetParent !== null) {
            window.app.fetchDriftMarkets();
        }
    }, 30000);
});
