/**
 * EngineManager
 * =============
 * Handles logic for Engine Control, Configuration, and State Management.
 */
export class EngineManager {
    constructor(app) {
        this.app = app;
    }

    /**
     * Update all engine states from SYSTEM_STATS
     */
    updateStates(states) {
        let runningCount = 0;

        Object.entries(states).forEach(([name, state]) => {
            if (this.app.engines[name]) {
                const engine = this.app.engines[name];
                // Check if it has setState method (EngineCard)
                if (typeof engine.setState === 'function') {
                    engine.setState(state);
                }

                // Cache state on the engine object itself if needed
                engine.state = state;

                if (state.status === 'running') runningCount++;
            }
        });

        if (this.app.headerStats) {
            this.app.headerStats.setEngineCount(runningCount, Object.keys(this.app.engines).length);
        }
    }

    /**
     * Toggle engine on/off
     */
    toggleEngine(engineName, currentStatus, mode) {
        const isRunning = currentStatus === 'running' || currentStatus === 'starting';

        if (isRunning) {
            this.app.ws.send('STOP_ENGINE', { engine: engineName });
            this.app.terminal.addLog('SYSTEM', 'INFO', `Stopping ${engineName} engine...`);
        } else {
            this.app.ws.send('START_ENGINE', { engine: engineName, mode: mode });
            this.app.terminal.addLog('SYSTEM', 'INFO',
                `Starting ${engineName} engine in ${mode.toUpperCase()} mode...`);
        }
    }

    /**
     * Handle engine command response
     */
    handleResponse(packet) {
        const { engine, result } = packet;
        const level = result.success ? 'SUCCESS' : 'ERROR';
        this.app.terminal.addLog('ENGINE', level, `${engine}: ${result.message}`);
    }

    /**
     * Save engine configuration
     */
    saveConfig(engineName, config) {
        this.app.ws.send('UPDATE_CONFIG', { engine: engineName, config });
        this.app.terminal.addLog('SYSTEM', 'INFO', `Updated config for ${engineName}`);
    }

    openSettings(engineId, config) {
        if (this.app.modal) {
            this.app.modal.openConfig(engineId, config);
        }
    }

    /**
     * Populate config panel based on engine type
     */
    populateConfigPanel(engineId) {
        const configGrid = document.getElementById('detail-config-grid');
        if (!configGrid) return;

        const engine = this.app.engines[engineId];
        const config = engine?.state?.config || {};

        const configFormatters = {
            'arb': {
                'min_spread': { label: 'Min Spread', format: v => `${v}%` },
                'max_trade_usd': { label: 'Max Trade', format: v => `$${v}` },
                'scan_interval': { label: 'Scan Interval', format: v => `${v}s` },
                'risk_tier': { label: 'Risk Tier', format: v => v.toUpperCase() }
            },
            'funding': {
                'leverage': { label: 'Leverage', format: v => `${v}x` },
                'watchdog_threshold': { label: 'Watchdog', format: v => `${(v * 100).toFixed(2)}%` },
                'rebalance_enabled': { label: 'Rebalance', format: v => v ? 'ON' : 'OFF' },
                'max_position_usd': { label: 'Max Position', format: v => `$${v}` }
            },
            'scalp': {
                'take_profit_pct': { label: 'Take Profit', format: v => `+${v}%` },
                'stop_loss_pct': { label: 'Stop Loss', format: v => `-${v}%` },
                'max_pods': { label: 'Max Pods', format: v => v },
                'sentiment_threshold': { label: 'Sentiment', format: v => `${(v * 100).toFixed(0)}%` }
            },
            'lst': {
                'peg_threshold': { label: 'Peg Threshold', format: v => `${v}%` },
                'exit_liquidity': { label: 'Exit Check', format: v => v ? 'ON' : 'OFF' }
            }
        };

        const formatters = configFormatters[engineId] || {};
        let html = '';

        Object.entries(config).forEach(([key, value]) => {
            const formatter = formatters[key];
            if (formatter) {
                html += `
                    <div class="config-item">
                        <div class="config-label">${formatter.label}</div>
                        <div class="config-value">${formatter.format(value)}</div>
                    </div>
                `;
            }
        });

        // Fallback if no config
        if (!html) {
            html = '<div class="config-item"><div class="config-label">No Config</div><div class="config-value">--</div></div>';
        }

        configGrid.innerHTML = html;
    }

    /**
     * Bind vault control button events (Detail View)
     */
    bindEngineControls(engineId) {
        // Reset Sim Button
        const resetBtn = document.querySelector('.vault-btn.reset');
        if (resetBtn) {
            resetBtn.onclick = () => {
                this.app.ws.send('VAULT_RESET', { engine: engineId });
                this.app.terminal.addLog('VAULT', 'WARNING', `Resetting ${engineId} vault...`);
            };
        }

        // Live Sync Button
        const syncBtn = document.querySelector('.vault-btn.sync');
        if (syncBtn) {
            syncBtn.onclick = () => {
                this.app.ws.send('VAULT_SYNC', { engine: engineId });
                this.app.terminal.addLog('VAULT', 'INFO', `Syncing ${engineId} vault from live wallet...`);
            };
        }

        // Power Toggle in Detail View
        const powerBtn = document.querySelector('.detail-power');
        if (powerBtn) {
            powerBtn.onclick = () => {
                const engine = this.app.engines[engineId];
                const mode = engine?.mode || 'paper';
                const status = engine?.state?.status || 'stopped';
                this.toggleEngine(engineId, status, mode);
            };
        }

        // Mode Selector in Detail View
        const modeSelector = document.querySelector('.detail-mode');
        if (modeSelector) {
            modeSelector.querySelectorAll('.mode-btn').forEach(btn => {
                btn.onclick = () => {
                    modeSelector.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    if (this.app.engines[engineId]) {
                        this.app.engines[engineId].setMode(btn.dataset.mode);
                    }
                };
            });
        }
    }

    /**
     * Update vault panel with data from WebSocket
     */
    updateVaultPanel(engineId, vaultData) {
        // Only update if we are viewing this engine
        if (this.app.viewManager && this.app.viewManager.currentDetailEngine !== engineId) {
            // Fallback if viewManager not available or logic differs
            if (this.app.currentDetailEngine !== engineId) return;
        }

        // Update equity
        const equityEl = document.getElementById('detail-vault-equity');
        if (equityEl) {
            equityEl.textContent = `$${(vaultData.equity || 0).toFixed(2)}`;
        }

        // Update asset rows
        const assetsContainer = document.getElementById('detail-vault-assets');
        if (assetsContainer && vaultData.assets) {
            let html = '';
            Object.entries(vaultData.assets).sort((a, b) => {
                // USDC first, then SOL, then others
                if (a[0] === 'USDC') return -1;
                if (b[0] === 'USDC') return 1;
                if (a[0] === 'SOL') return -1;
                if (b[0] === 'SOL') return 1;
                return 0;
            }).forEach(([asset, balance]) => {
                const displayBal = balance >= 1 ? balance.toFixed(2) : balance.toFixed(4);
                html += `
                    <div class="vault-asset-row">
                        <span class="vault-asset-symbol">${asset}</span>
                        <span class="vault-asset-balance">${displayBal}</span>
                    </div>
                `;
            });
            assetsContainer.innerHTML = html || '<div class="vault-asset-row"><span>No assets</span></div>';
        }
    }
}
