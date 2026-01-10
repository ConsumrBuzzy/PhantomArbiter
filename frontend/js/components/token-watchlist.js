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
                <span class="panel-title">Token Watchlist</span>
                <span class="watchlist-count">0 tokens</span>
            </div>
            <div class="watchlist-table-wrapper">
                <table class="watchlist-table">
                    <thead>
                        <tr>
                            <th>TOKEN</th>
                            <th>PRICE</th>
                            <th>24H</th>
                            <th>SPREAD</th>
                            <th>VENUES</th>
                        </tr>
                    </thead>
                    <tbody id="watchlist-tbody">
                        <tr>
                            <td colspan="5" class="loading-row">Loading tokens...</td>
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

        // Sort by volume descending
        const sorted = [...data.tokens].sort((a, b) =>
            (b.volume_24h || 0) - (a.volume_24h || 0)
        );

        // Build table rows
        this.tbody.innerHTML = sorted.map(token => this.renderRow(token)).join('');
    }

    /**
     * Render a single token row
     */
    renderRow(token) {
        const price = token.best_ask || Object.values(token.prices || {})[0] || 0;
        const change = token.change_24h || 0;
        const spread = token.spread_pct || 0;
        const venues = Object.keys(token.prices || {});

        // Format price (handle very small numbers)
        let priceStr;
        if (price === 0) {
            priceStr = '--';
        } else if (price < 0.0001) {
            priceStr = `$${price.toExponential(2)}`;
        } else if (price < 1) {
            priceStr = `$${price.toFixed(6)}`;
        } else {
            priceStr = `$${price.toFixed(2)}`;
        }

        // Color classes
        const changeClass = change >= 0 ? 'positive' : 'negative';
        const spreadClass = spread > 0.5 ? 'spread-hot' : '';

        // Category badge colors
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
                <td class="price-cell">${priceStr}</td>
                <td class="change-cell ${changeClass}">
                    ${change >= 0 ? '+' : ''}${change.toFixed(1)}%
                </td>
                <td class="spread-cell ${spreadClass}">
                    ${spread > 0 ? spread.toFixed(2) + '%' : '--'}
                </td>
                <td class="venues-cell">
                    ${venues.slice(0, 3).map(v => `<span class="venue-badge">${v.slice(0, 3)}</span>`).join('')}
                </td>
            </tr>
        `;
    }
}

export default TokenWatchlist;
