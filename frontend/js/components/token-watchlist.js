/**
 * Token Watchlist Component
 * =========================
 * Displays multi-token price tracking across DEX venues.
 */

export class TokenWatchlist {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.tokens = new Map();

        if (this.container) {
            this.render();
        }
    }

    /**
     * Initial render of table structure
     */
    render() {
        this.container.innerHTML = `
            <div class="watchlist-header">
                <span class="panel-title">Token Matrix (Arb View)</span>
                <span class="watchlist-count">0 tokens</span>
            </div>
            <div class="watchlist-table-wrapper">
                <table class="watchlist-table matrix-view">
                    <thead>
                        <tr>
                            <th style="width: 25%">ASSET</th>
                            <th style="width: 20%">RAYDIUM</th>
                            <th style="width: 20%">ORCA</th>
                            <th style="width: 20%">METEORA</th>
                            <th style="width: 15%">SPREAD</th>
                        </tr>
                    </thead>
                    <tbody id="watchlist-tbody">
                        <tr>
                            <td colspan="5" class="loading-row">Loading matrix...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        `;

        this.tbody = document.getElementById('watchlist-tbody');
        this.countEl = this.container.querySelector('.watchlist-count');
    }

    /**
     * Update with new token data
     */
    update(data) {
        if (!data.tokens || !this.tbody) return;

        // Update count
        if (this.countEl) {
            this.countEl.textContent = `${data.tokens.length} tokens`;
        }

        // Sort by spread descending (hottest arbs first)
        const sorted = [...data.tokens].sort((a, b) =>
            (b.spread_pct || 0) - (a.spread_pct || 0)
        );

        // Build table rows
        this.tbody.innerHTML = sorted.map(token => this.renderRow(token)).join('');
    }

    /**
     * Render a single token row (Matrix Style)
     */
    renderRow(token) {
        const rayPrice = token.prices['raydium'] || 0;
        const orcaPrice = token.prices['orca'] || 0;
        const metPrice = token.prices['meteora'] || 0;
        const spread = token.spread_pct || 0;

        // Helper to format price cell
        const formatPriceCell = (price, isBest, isWorst) => {
            if (!price) return '<span class="price-empty">--</span>';

            let className = 'price-val';
            if (isBest) className += ' price-best'; // Sell here (highest)
            if (isWorst) className += ' price-worst'; // Buy here (lowest)

            // Format number
            let priceStr;
            if (price < 0.0001) priceStr = price.toExponential(2);
            else if (price < 1) priceStr = price.toFixed(5);
            else priceStr = price.toFixed(2);

            return `<span class="${className}">$${priceStr}</span>`;
        };

        // Find min/max for highlighting
        const prices = [rayPrice, orcaPrice, metPrice].filter(p => p > 0);
        const maxPrice = Math.max(...prices);
        const minPrice = Math.min(...prices);

        // Spread styling
        const spreadClass = spread > 0.5 ? 'spread-hot' : '';
        const spreadIcon = spread > 1.0 ? '🔥' : '';

        // Category color
        const categoryColors = {
            'major': 'var(--neon-blue)',
            'meme': 'var(--neon-gold)',
            'ai': 'var(--neon-green)'
        };
        const categoryColor = categoryColors[token.category] || 'var(--text-dim)';

        return `
            <tr class="token-row" data-symbol="${token.symbol}">
                <td class="token-cell">
                    <span class="token-symbol">${token.symbol}</span>
                    <span class="token-category" style="color: ${categoryColor}">${token.category}</span>
                </td>
                
                <td class="matrix-cell">
                    ${formatPriceCell(rayPrice, rayPrice === maxPrice && spread > 0, rayPrice === minPrice && spread > 0)}
                </td>
                
                <td class="matrix-cell">
                    ${formatPriceCell(orcaPrice, orcaPrice === maxPrice && spread > 0, orcaPrice === minPrice && spread > 0)}
                </td>
                
                <td class="matrix-cell">
                    ${formatPriceCell(metPrice, metPrice === maxPrice && spread > 0, metPrice === minPrice && spread > 0)}
                </td>
                
                <td class="spread-cell ${spreadClass}">
                    ${spread > 0 ? `${spread.toFixed(2)}% ${spreadIcon}` : '--'}
                </td>
            </tr>
        `;
    }
}

export default TokenWatchlist;
