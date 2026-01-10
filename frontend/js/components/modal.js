/**
 * Modal Manager
 * =============
 * Manages modal dialogs (settings, SOS confirmation).
 */

export class ModalManager {
    constructor() {
        this.settingsModal = document.getElementById('settings-modal');
        this.sosModal = document.getElementById('sos-modal');
        this.currentEngine = null;

        // Callbacks
        this.onSaveConfig = null;
        this.onSOS = null;

        this.bindEvents();
    }

    /**
     * Bind modal events
     */
    bindEvents() {
        // Close buttons
        document.querySelectorAll('.modal-close, [data-action="cancel"]').forEach(btn => {
            btn.addEventListener('click', () => this.closeAll());
        });

        // Save config
        document.querySelector('[data-action="save"]')?.addEventListener('click', () => {
            if (this.onSaveConfig) {
                const config = this.getFormConfig();
                this.onSaveConfig(this.currentEngine, config);
            }
            this.closeAll();
        });

        // SOS confirm
        document.querySelector('[data-action="confirm-sos"]')?.addEventListener('click', () => {
            if (this.onSOS) this.onSOS();
            this.closeAll();
        });

        // Close on overlay click
        document.querySelectorAll('.modal-overlay').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) this.closeAll();
            });
        });

        // ESC key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeAll();
        });
    }

    /**
     * Open settings modal for engine
     */
    openSettings(engineName, config) {
        this.currentEngine = engineName;

        const title = document.getElementById('modal-engine-name');
        const form = document.getElementById('modal-config-form');

        if (title) title.textContent = `${engineName.toUpperCase()} Settings`;
        if (form) form.innerHTML = this.generateFormFields(engineName, config);

        this.settingsModal?.classList.add('active');
    }

    /**
     * Open SOS confirmation modal
     */
    openSOS() {
        this.sosModal?.classList.add('active');
    }

    /**
     * Close all modals
     */
    closeAll() {
        document.querySelectorAll('.modal-overlay').forEach(modal => {
            modal.classList.remove('active');
        });
        this.currentEngine = null;
    }

    /**
     * Get form config values
     */
    getFormConfig() {
        const form = document.getElementById('modal-config-form');
        const config = {};

        form?.querySelectorAll('input, select').forEach(input => {
            const name = input.name;
            if (input.type === 'checkbox') {
                config[name] = input.checked;
            } else if (input.type === 'number') {
                config[name] = parseFloat(input.value);
            } else {
                config[name] = input.value;
            }
        });

        return config;
    }

    /**
     * Generate form fields for engine config
     */
    generateFormFields(engineName, currentConfig) {
        const schema = this.getConfigSchema(engineName);

        return Object.entries(schema).map(([key, meta]) => {
            const value = currentConfig?.[key] ?? meta.default;
            return `
                <div class="form-group">
                    <label class="form-label">${meta.label}</label>
                    <input type="${meta.type}"
                           name="${key}"
                           value="${value}"
                           class="form-input"
                           ${meta.step ? `step="${meta.step}"` : ''}
                           ${meta.min !== undefined ? `min="${meta.min}"` : ''}
                           ${meta.max !== undefined ? `max="${meta.max}"` : ''}>
                </div>
            `;
        }).join('');
    }

    /**
     * Get config schema for engine type
     */
    getConfigSchema(engineName) {
        const schemas = {
            arb: {
                min_spread: { label: 'Min Spread (%)', type: 'number', default: 0.5, step: 0.01 },
                max_trade_usd: { label: 'Max Trade ($)', type: 'number', default: 100 },
                scan_interval: { label: 'Scan Interval (s)', type: 'number', default: 2 },
                risk_tier: { label: 'Risk Tier', type: 'text', default: 'all' }
            },
            funding: {
                leverage: { label: 'Target Leverage', type: 'number', default: 1.0, step: 0.1, max: 3 },
                watchdog_threshold: { label: 'Watchdog Threshold', type: 'number', default: -0.01, step: 0.001 },
                rebalance_enabled: { label: 'Auto-Rebalance', type: 'checkbox', default: true }
            },
            scalp: {
                max_position_usd: { label: 'Max Position ($)', type: 'number', default: 50 },
                take_profit_pct: { label: 'Take Profit (%)', type: 'number', default: 5, step: 0.5 },
                stop_loss_pct: { label: 'Stop Loss (%)', type: 'number', default: 3, step: 0.5 },
                max_pods: { label: 'Max Pods', type: 'number', default: 5, min: 1, max: 10 },
                sentiment_threshold: { label: 'Sentiment Gate', type: 'number', default: 0.6, step: 0.05, min: 0, max: 1 }
            }
        };

        return schemas[engineName] || {};
    }
}

export default ModalManager;
