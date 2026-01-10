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
                break;

            case 'SCALP_SIGNAL':
                this.updateIntelTable('SCALP', data);
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

        if (isRunning) {
            this.sendCommand('STOP_ENGINE', { engine: engineName });
            this.addLog('SYSTEM', 'INFO', `Stopping ${engineName} engine...`);
        } else {
            this.sendCommand('START_ENGINE', { engine: engineName });
            this.addLog('SYSTEM', 'INFO', `Starting ${engineName} engine...`);
        }
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
}

// ═══════════════════════════════════════════════════════════════
// GLOBAL INIT
// ═══════════════════════════════════════════════════════════════

window.addEventListener('load', () => {
    window.app = new DashboardApp();
});
