/**
 * Split Inventory Component
 * =========================
 * Displays BOTH Live and Paper wallet assets side by side.
 */
export class Inventory {
    constructor() {
        // Get both table bodies
        this.liveTableBody = document.querySelector('#live-inventory-table tbody');
        this.paperTableBody = document.querySelector('#paper-inventory-table tbody');
        this.scalpTableBody = document.querySelector('#scalp-inventory-table tbody');

        // Store last data for re-rendering
        this.lastLiveData = null;
        this.lastPaperData = null;
    }

    /**
     * Update with wallet data from SYSTEM_STATS
     * @param {Object} data - Contains live_wallet and paper_wallet
     */
    update(data) {
        if (data.live_wallet) {
            this.lastLiveData = data.live_wallet;
            this.renderTable(this.liveTableBody, data.live_wallet, 'live');
        }
        if (data.paper_wallet || data.wallet) {
            this.lastPaperData = data.paper_wallet || data.wallet;
            this.renderTable(this.paperTableBody, this.lastPaperData, 'paper');
        }
    }

    /**
     * Update Scalp Vault
     */
    updateScalp(walletData) {
        if (!walletData) return;
        this.renderTable(this.scalpTableBody, walletData, 'scalp');
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
