/**
 * Inventory Component
 * Displays wallet assets and balances.
 */
export class Inventory {
    constructor(tableId) {
        this.tableBody = document.querySelector(`#${tableId} tbody`);
        this.context = 'GLOBAL'; // GLOBAL, ARB, SCALP, FUNDING, LST

        // Define relevant assets per context (others hidden unless non-zero)
        this.relevantAssets = {
            'ARB': ['SOL', 'USDC'],
            'FUNDING': ['USDC', 'SOL'],
            'SCALP': ['SOL', 'USDC', 'WIF', 'BONK', 'POPCAT'],
            'LST': ['SOL', 'mSOL', 'jitoSOL', 'bSOL']
        };
    }

    setContext(context) {
        this.context = context ? context.toUpperCase() : 'GLOBAL';
        this.render(); // Re-render with existing data if available
    }

    update(walletData) {
        if (!this.tableBody || !walletData) return;
        this.lastData = walletData; // Store for re-rendering on context switch
        this.render();
    }

    render() {
        if (!this.lastData) return;

        this.tableBody.innerHTML = '';

        const assets = this.lastData.assets || {
            'SOL': this.lastData.sol_balance,
            'USDC': this.lastData.usdc_balance
        };

        // Sort: USDC first, then SOL, then others
        const sortedAssets = Object.entries(assets).sort((a, b) => {
            if (a[0] === 'USDC') return -1;
            if (b[0] === 'USDC') return 1;
            if (a[0] === 'SOL') return -1;
            if (b[0] === 'SOL') return 1;
            return a[0].localeCompare(b[0]);
        });

        sortedAssets.forEach(([asset, data]) => {
            const amount = (typeof data === 'object' && data !== null) ? data.amount : data;
            const valueUsd = (typeof data === 'object' && data !== null) ? data.value_usd : 0;

            // ADAPTIVE FILTERING
            // Always show non-dust balances (> $1 value or > 0.01 amount)
            // If balance is zero/dust, ONLY show if relevant to current Context
            const isDust = valueUsd < 1.0 && amount < 0.01;
            const isRelevant = this.context === 'GLOBAL' ||
                (this.relevantAssets[this.context] && this.relevantAssets[this.context].includes(asset));

            if (isDust && !isRelevant) return;

            const tr = document.createElement('tr');

            // Value Display
            let valDisplay = '--';
            if (valueUsd > 0) {
                valDisplay = `$${valueUsd.toFixed(2)}`;
            } else if (asset === 'USDC') {
                valDisplay = `$${amount.toFixed(2)}`;
            }

            // Highlight relevant assets in context
            const highlightClass = (this.context !== 'GLOBAL' && isRelevant) ? 'text-neon-blue' : '';
            if (highlightClass) tr.style.background = 'rgba(0, 212, 255, 0.05)';

            tr.innerHTML = `
                <td class="${highlightClass}"><span class="token-icon ${asset.toLowerCase()}"></span> ${asset}</td>
                <td class="mono ${highlightClass}">${amount.toFixed(4)}</td>
                <td class="mono">${valDisplay}</td>
            `;
            this.tableBody.appendChild(tr);
        });
    }
}
