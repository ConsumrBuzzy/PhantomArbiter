/**
 * Inventory Component
 * Displays wallet assets with price history and change indicators.
 * 
 * Enhanced with: Current Price, 5m/1h/24h changes for storytelling.
 */
export class Inventory {
    constructor(tableId) {
        this.tableBody = document.querySelector(`#${tableId} tbody`);
        this.tableHead = document.querySelector(`#${tableId} thead tr`);
        this.context = 'GLOBAL'; // GLOBAL, ARB, SCALP, FUNDING, LST

        // Define relevant assets per context (others hidden unless non-zero)
        this.relevantAssets = {
            'ARB': ['SOL', 'USDC'],
            'FUNDING': ['USDC', 'SOL'],
            'SCALP': ['SOL', 'USDC', 'WIF', 'BONK', 'POPCAT'],
            'LST': ['SOL', 'mSOL', 'jitoSOL', 'bSOL']
        };

        // Update table headers on init
        this.initHeaders();
    }

    initHeaders() {
        if (!this.tableHead) return;
        this.tableHead.innerHTML = `
            <th>ASSET</th>
            <th>AMOUNT</th>
            <th>PRICE</th>
            <th>VALUE</th>
            <th style="text-align: center;">5m</th>
            <th style="text-align: center;">1h</th>
            <th style="text-align: center;">24h</th>
        `;
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

    /**
     * Format change as colored arrow indicator
     */
    formatChange(pct) {
        if (pct === undefined || pct === null || isNaN(pct)) {
            return `<span style="color: var(--text-dim);">--</span>`;
        }

        const absVal = Math.abs(pct);
        let color, arrow;

        if (pct > 0.5) {
            color = 'var(--neon-green)';
            arrow = absVal > 3 ? '▲▲' : '▲';
        } else if (pct < -0.5) {
            color = 'var(--neon-red)';
            arrow = absVal > 3 ? '▼▼' : '▼';
        } else {
            color = 'var(--text-dim)';
            arrow = '→';
        }

        return `<span style="color: ${color}; font-size: 0.75rem;" title="${pct.toFixed(2)}%">${arrow}</span>`;
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
            const price = (typeof data === 'object' && data !== null) ? data.price : null;

            // Mock price changes for demo (will be replaced with real data)
            const change5m = (typeof data === 'object' && data !== null) ? data.change_5m : null;
            const change1h = (typeof data === 'object' && data !== null) ? data.change_1h : null;
            const change24h = (typeof data === 'object' && data !== null) ? data.change_24h : null;

            // ADAPTIVE FILTERING
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

            // Price Display
            let priceDisplay = '--';
            if (asset === 'USDC') {
                priceDisplay = '$1.00';
            } else if (price && price > 0) {
                priceDisplay = price > 1 ? `$${price.toFixed(2)}` : `$${price.toFixed(4)}`;
            }

            // Highlight relevant assets in context
            const highlightClass = (this.context !== 'GLOBAL' && isRelevant) ? 'text-neon-blue' : '';
            if (highlightClass) tr.style.background = 'rgba(0, 212, 255, 0.05)';

            tr.innerHTML = `
                <td class="${highlightClass}"><span class="token-icon ${asset.toLowerCase()}"></span> ${asset}</td>
                <td class="mono ${highlightClass}">${amount.toFixed(4)}</td>
                <td class="mono">${priceDisplay}</td>
                <td class="mono">${valDisplay}</td>
                <td style="text-align: center;">${this.formatChange(change5m)}</td>
                <td style="text-align: center;">${this.formatChange(change1h)}</td>
                <td style="text-align: center;">${this.formatChange(change24h)}</td>
            `;
            this.tableBody.appendChild(tr);
        });
    }
}
