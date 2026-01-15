/**
 * Layout Manager
 * ==============
 * Manages the visibility and layout of dashboard components.
 * Persists user preferences to localStorage.
 */

export class LayoutManager {
    constructor(options = {}) {
        this.storageKey = 'phantom_layout_config';
        this.config = this.loadConfig();
        this.components = {}; // Map id -> element

        // Define registered component IDs that can be toggled
        this.registeredIds = [
            'whale-tape-container',
            'inventory-panel',
            'watchlist-panel',
            'intel-panel',
            'metrics-panel',
            'view-scanner', // Can toggle entire views too if we want
            'engine-grid',
            'drift-panel'
        ];

        this.init();
    }

    /**
     * Load config from local storage or use defaults
     */
    loadConfig() {
        const stored = localStorage.getItem(this.storageKey);
        if (stored) {
            try {
                const config = JSON.parse(stored);
                // Force critical panels to be visible (Recovery Mode)
                config['watchlist-panel'] = true;
                config['drift-panel'] = true;
                return config;
            } catch (e) {
                console.error("Failed to parse layout config", e);
            }
        }

        // Default Config: All Visible
        return {
            'whale-tape-container': true,
            'inventory-panel': true,
            'watchlist-panel': true,
            'intel-panel': true,
            'metrics-panel': true,
        };
    }

    /**
     * Save current config to local storage
     */
    saveConfig() {
        localStorage.setItem(this.storageKey, JSON.stringify(this.config));
    }

    /**
     * Initialize manager
     */
    init() {
        // Find elements
        this.registeredIds.forEach(id => {
            const el = document.getElementById(id) || document.querySelector(`.${id}`);
            if (el) {
                this.components[id] = el;
                // Apply initial state
                this.setVisibility(id, this.config[id] !== false);
            }
        });

        this.injectOptionsButton();
    }

    /**
     * Refresh component references (call after dynamic view load)
     */
    refresh() {
        this.registeredIds.forEach(id => {
            const el = document.getElementById(id) || document.querySelector(`.${id}`);
            if (el) {
                this.components[id] = el;
                // Re-apply state
                this.setVisibility(id, this.config[id] !== false);
            }
        });
    }

    /**
     * Set visibility of a component
     */
    setVisibility(id, isVisible) {
        const el = this.components[id];
        if (!el) return;

        if (isVisible) {
            el.style.display = ''; // Reset to default (flex/block)
            el.classList.remove('hidden-component');
        } else {
            el.style.display = 'none';
            el.classList.add('hidden-component');
        }

        this.config[id] = isVisible;
        this.saveConfig();
    }

    /**
     * Toggle a component
     */
    toggle(id) {
        const current = this.config[id] !== false;
        this.setVisibility(id, !current);
        return !current;
    }

    /**
     * Inject the "View Options" button into the header or nav
     */
    injectOptionsButton() {
        const nav = document.querySelector('.sidebar');
        if (!nav) return;

        const optionsBtn = document.createElement('div');
        optionsBtn.className = 'nav-item';
        optionsBtn.dataset.view = 'options';
        optionsBtn.dataset.tooltip = 'Layout';
        optionsBtn.innerHTML = '👁️';
        optionsBtn.title = 'Customize Layout';

        optionsBtn.addEventListener('click', () => this.openOptionsModal());

        // Insert before Config or at bottom
        const configBtn = nav.querySelector('[data-view="config"]');
        if (configBtn) {
            nav.insertBefore(optionsBtn, configBtn);
        } else {
            nav.appendChild(optionsBtn);
        }
    }

    /**
     * Open the Options Modal
     */
    openOptionsModal() {
        // Create modal content dynamically
        const modalId = 'layout-options-modal';
        let modal = document.getElementById(modalId);

        if (!modal) {
            modal = this.createModalElement(modalId);
            document.body.appendChild(modal);
        }

        const list = modal.querySelector('.options-list');
        list.innerHTML = ''; // Clear

        Object.keys(this.components).forEach(id => {
            const isVisible = this.config[id] !== false;
            const item = document.createElement('div');
            item.className = 'option-item';
            item.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.1);';

            const label = id.replace(/-/g, ' ').toUpperCase().replace('CONTAINER', '').replace('PANEL', '');

            item.innerHTML = `
                <span style="font-family: 'Roboto Mono', monospace;">${label}</span>
                <label class="switch-toggle">
                    <input type="checkbox" ${isVisible ? 'checked' : ''} data-target="${id}">
                    <span class="slider round"></span>
                </label>
            `;

            item.querySelector('input').addEventListener('change', (e) => {
                this.setVisibility(id, e.target.checked);
            });

            list.appendChild(item);
        });

        modal.classList.add('active');

        // Close handler
        const closer = () => modal.classList.remove('active');
        modal.querySelector('.modal-close').onclick = closer;
        modal.querySelector('.btn-primary').onclick = closer;
        window.onclick = (e) => { if (e.target === modal) closer(); };
    }

    createModalElement(id) {
        const div = document.createElement('div');
        div.id = id;
        div.className = 'modal-overlay';
        div.innerHTML = `
            <div class="modal-content" style="max-width: 400px;">
                <div class="modal-header">
                    <span class="modal-title">Customize Layout</span>
                    <button class="modal-close">✕</button>
                </div>
                <div class="modal-body">
                    <div class="options-list"></div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary">Done</button>
                </div>
            </div>
        `;
        return div;
    }
}
