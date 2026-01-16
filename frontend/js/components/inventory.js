/**
 * Split Inventory Component
 * =========================
 * Displays BOTH Live and Paper wallet assets side by side.
 */
export class Inventory {
    constructor() {
        // Get fixed table bodies
        this.liveTableBody = document.querySelector('#live-inventory-table tbody');
        // this.paperTableBody = document.querySelector('#paper-inventory-table tbody');

        // Container for dynamic strategy vaults
        this.container = document.querySelector('#inventory-container');

        // Track created vault elements
        this.vaultElements = new Set();
    }

    /**
     * Update with wallet data from SYSTEM_STATS
     * @param {Object} data - SYSTEM_STATS packet
     */
    update(data) {
        // 1. Update Fixed Tables
        if (data.live_wallet) {
            this.renderTable(this.liveTableBody, data.live_wallet, 'live');
        }
        // Removed legacy global paper wallet rendering per user request
        // if (data.paper_wallet || data.wallet) { ... }

        // 2. Update Dynamic Strategy Vaults
        if (data.vaults) {
            Object.entries(data.vaults).forEach(([engineName, vaultData]) => {
                this.updateStrategyVault(engineName, vaultData);
            });
        }


        // 3. Update Active Engine Label on Live Inventory
        this.updateLiveLabel(data.engines);
    }

    /**
     * Update Live Inventory Label if an engine is actively using it
     */
    updateLiveLabel(engines) {
        const liveLabel = document.querySelector('.inventory-half.live .inventory-label');
        if (!liveLabel) return;

        // Find active live engine (excluding Drift which has dedicated vault)
        let activeEngine = null;
        if (engines) {
            for (const [name, info] of Object.entries(engines)) {
                if (info.status === 'running' && info.mode === 'live' && name !== 'drift') {
                    activeEngine = name;
                    break;
                }
            }
        }

        if (activeEngine) {
            liveLabel.innerHTML = `🔴 LIVE <span style="font-size: 0.7em; background: var(--neon-gold); color: black; padding: 2px 6px; border-radius: 4px; margin-left: 10px; vertical-align: middle;">⚡ ${activeEngine.toUpperCase()} ACTIVE</span>`;
        } else {
            liveLabel.innerHTML = `🔴 LIVE`;
        }
    }

    /**
     * Create or Update a Strategy Vault Table
     */
    updateStrategyVault(engineName, vaultData, engineInfo) {
        const vaultId = `vault-${engineName}`;
        let tbody = document.querySelector(`#${vaultId} tbody`);

        // Create if missing
        if (!tbody) {
            this.createVaultElement(engineName, vaultId, vaultData.type);
            tbody = document.querySelector(`#${vaultId} tbody`);
        }

        // Update Label with Active Badge if applicable
        this.updateVaultLabel(engineName, vaultId, vaultData.type, engineInfo);

        this.renderTable(tbody, vaultData, engineName);
    }

    updateVaultLabel(engineName, vaultId, type, engineInfo) {
        const wrapper = document.getElementById(`wrapper-${vaultId}`);
        if (!wrapper) return;
        const labelEl = wrapper.querySelector('.inventory-label');
        if (!labelEl) return;

        // Base Label
        const color = type === 'ON_CHAIN' ? 'var(--neon-purple)' : 'var(--neon-gold)';
        let labelText = type === 'ON_CHAIN' ? `🔗 ${engineName.toUpperCase()} (LINKED)` : `⚡ ${engineName.toUpperCase()} (PAPER)`;

        // Check for Active Status
        // Active if engine is running AND matches the vault type mode
        // Virtual Vault is active if engine mode is 'paper'
        // OnChain Vault is active if engine mode is 'live'
        let isActive = false;
        if (engineInfo && engineInfo.status === 'running') {
            if (type === 'VIRTUAL' && engineInfo.mode === 'paper') isActive = true;
            if (type === 'ON_CHAIN' && engineInfo.mode === 'live') isActive = true;
        }

        if (isActive) {
            labelText += ` <span style="font-size: 0.7em; background: ${color}; color: black; padding: 2px 6px; border-radius: 4px; margin-left: 10px; vertical-align: middle;">ACTIVE</span>`;
        }

        labelEl.innerHTML = labelText;
        labelEl.style.color = color;
    }

    createVaultElement(engineName, vaultId, type) {
        if (!this.container) return;

        const wrapper = document.createElement('div');
        wrapper.className = 'inventory-half'; // Reuse style class
        wrapper.style.borderLeft = '1px solid rgba(255,255,255,0.05)';
        wrapper.style.paddingLeft = '10px';
        wrapper.id = `wrapper-${vaultId}`;

        // Initial Label (will be updated by updateStrategyVault)
        wrapper.innerHTML = `
            <div class="inventory-label">Loading...</div>
            <table id="${vaultId}">
                <thead>
                    <tr>
                        <th>ASSET</th>
                        <th>AMOUNT</th>
                        <th>VALUE</th>
                    </tr>
                </thead>
                <tbody>
                    <tr><td colspan="3">Loading...</td></tr>
                </tbody>
            </table>
        `;

        this.container.appendChild(wrapper);
    }

    /**
     * Render assets into a specific table
     */
    renderTable(tbody, walletData, type) {
        if (!tbody || !walletData) return;

        tbody.innerHTML = '';

        const assets = walletData.assets || {};

        // Check if empty
        if (Object.keys(assets).length === 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td colspan="3" style="text-align: center; color: var(--text-dim);">No assets</td>`;
            tbody.appendChild(tr);
            return;
        }

        // Sort: USDC first, then SOL, then others by value
        const sortedAssets = Object.entries(assets).sort((a, b) => {
            if (a[0] === 'USDC') return -1;
            if (b[0] === 'USDC') return 1;
            if (a[0] === 'SOL') return -1;
            if (b[0] === 'SOL') return 1;
            return (b[1].value_usd || 0) - (a[1].value_usd || 0);
        });

        sortedAssets.forEach(([asset, data]) => {
            const amount = (typeof data === 'object') ? data.amount : data;
            const valueUsd = (typeof data === 'object') ? data.value_usd : 0;

            // Skip dust
            if (valueUsd < 0.01 && amount < 0.0001) return;

            const tr = document.createElement('tr');

            // Format value
            let valDisplay = valueUsd > 0 ? `$${valueUsd.toFixed(2)}` : '--';

            // Format amount based on size
            let amtDisplay = amount >= 1 ? amount.toFixed(2) : amount.toFixed(4);

            tr.innerHTML = `
                <td><span class="token-symbol">${asset}</span></td>
                <td class="mono">${amtDisplay}</td>
                <td class="mono">${valDisplay}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Legacy method for backward compatibility
    setContext(context) {
        // No-op in split view
    }
}
