/**
 * Engine Card Component
 * =====================
 * Manages individual engine cards and their controls.
 */

export class EngineCard {
    constructor(engineName, options = {}) {
        this.name = engineName;
        this.card = document.querySelector(`.engine-card[data-engine="${engineName}"]`);
        this.state = { status: 'stopped', config: {} };
        this.mode = 'paper'; // paper or live

        // Callbacks
        this.onToggle = options.onToggle || (() => { });
        this.onSettings = options.onSettings || (() => { });
        this.onModeChange = options.onModeChange || (() => { });

        if (this.card) {
            this.bindEvents();
        }
    }

    /**
     * Bind card events
     */
    bindEvents() {
        // Power toggle
        const powerBtn = this.card.querySelector('.power-toggle');
        if (powerBtn) {
            powerBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.onToggle(this.name, this.state.status, this.mode);
            });
        }

        // Settings button
        const settingsBtn = this.card.querySelector('.settings-btn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.onSettings(this.name, this.state.config);
            });
        }

        // Mode selector buttons
        const modeSelector = this.card.querySelector('.mode-selector');
        if (modeSelector) {
            modeSelector.querySelectorAll('.mode-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.setMode(btn.dataset.mode);
                });
            });
        }
    }

    /**
     * Update engine state
     */
    setState(state) {
        this.state = state;

        if (!this.card) return;

        // Update status attribute
        this.card.dataset.status = state.status;

        // Update status text
        const statusText = this.card.querySelector('.status-text');
        if (statusText) {
            statusText.textContent = this.formatStatus(state.status);
        }

        // Update uptime
        const uptimeEl = this.card.querySelector('.status-uptime');
        if (uptimeEl && state.uptime_seconds) {
            uptimeEl.textContent = this.formatUptime(state.uptime_seconds);
        } else if (uptimeEl) {
            uptimeEl.textContent = '';
        }

        // Update config display
        if (state.config) {
            this.updateConfigDisplay(state.config);
        }
    }

    /**
     * Set execution mode (paper/live)
     */
    setMode(mode) {
        this.mode = mode;

        // Update UI buttons
        const selector = this.card.querySelector('.mode-selector');
        if (selector) {
            selector.querySelectorAll('.mode-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.mode === mode);
            });
        }

        this.onModeChange(this.name, mode);
    }

    /**
     * Get current mode
     */
    getMode() {
        return this.mode;
    }

    /**
     * Check if engine is running
     */
    isRunning() {
        return this.state.status === 'running' || this.state.status === 'starting';
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
     * Update config values display
     */
    updateConfigDisplay(config) {
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
            const el = this.card.querySelector(`[data-config="${key}"]`);
            if (el && formatters[key]) {
                el.textContent = formatters[key](value);
            }
        });
    }
}

export default EngineCard;
