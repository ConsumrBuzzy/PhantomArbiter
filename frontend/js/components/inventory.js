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

        sortedAssets.forEach(([asset, balance]) => {
            if (balance <= 0.00001 && asset !== 'SOL' && asset !== 'USDC') return;

            const tr = document.createElement('tr');

            // Basic value estimation
            let valDisplay = '--';
            if (asset === 'USDC') {
                valDisplay = `$${balance.toFixed(2)}`;
            } else if (asset === 'SOL') {
                valDisplay = `◎${balance.toFixed(2)}`;
            }

            tr.innerHTML = `
                <td><span class="token-icon ${asset.toLowerCase()}"></span> ${asset}</td>
                <td class="mono">${balance.toFixed(4)}</td>
                <td class="mono">${valDisplay}</td>
            `;
            this.tableBody.appendChild(tr);
        });
    }
}
