/**
 * Inventory Component
 * Displays wallet assets and balances.
 */
export class Inventory {
    constructor(tableId) {
        this.tableBody = document.querySelector(`#${tableId} tbody`);
    }

    update(walletData) {
        if (!this.tableBody || !walletData) return;

        this.tableBody.innerHTML = '';

        const assets = walletData.assets || {
            'SOL': walletData.sol_balance,
            'USDC': walletData.usdc_balance
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
            // Support both simple number (legacy) and enriched object
            const amount = (typeof data === 'object' && data !== null) ? data.amount : data;
            const valueUsd = (typeof data === 'object' && data !== null) ? data.value_usd : 0;

            if (amount <= 0.00001 && asset !== 'SOL' && asset !== 'USDC') return;

            const tr = document.createElement('tr');

            // Value Display
            let valDisplay = '--';
            if (valueUsd > 0) {
                valDisplay = `$${valueUsd.toFixed(2)}`;
            } else if (asset === 'USDC') {
                valDisplay = `$${amount.toFixed(2)}`;
            }

            tr.innerHTML = `
                <td><span class="token-icon ${asset.toLowerCase()}"></span> ${asset}</td>
                <td class="mono">${amount.toFixed(4)}</td>
                <td class="mono">${valDisplay}</td>
            `;
            this.tableBody.appendChild(tr);
        });
    }
}
