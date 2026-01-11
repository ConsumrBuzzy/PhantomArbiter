/**
 * Meme Sniper Strip Component
 * ===========================
 * Displays high-velocity meme token opportunities in the header.
 * Horizontal scrolling strip of "hot cards".
 */

export class MemeSniperStrip {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.tokens = [];
    }

    /**
     * Update with token watchlist data
     * @param {Object} data - Contains 'tokens' array (from TOKEN_WATCHLIST packet)
     */
    update(data) {
        if (!this.container || !data.tokens) return;

        // Filter and sort for "hot" tokens
        // Sort by spread descending
        const hotTokens = [...data.tokens]
            .sort((a, b) => (b.spread_pct || 0) - (a.spread_pct || 0))
            .slice(0, 50); // Show top 50 (Main View)

        // If no tokens yet, keep loading or show empty state
        if (hotTokens.length === 0) {
            if (!this.container.querySelector('.sniper-loading')) {
                this.container.innerHTML = '<div class="sniper-loading">Scanning Mempool...</div>';
            }
            return;
        }

        this.render(hotTokens);
    }

    render(tokens) {
        const checkIcon = '✓';

        const cardsHtml = tokens.map(token => {
            const spread = token.spread_pct || 0;
            const isHot = spread > 1.0;
            const hotClass = isHot ? 'hot' : '';

            // Determine best buy/sell venues
            const prices = token.prices || {};
            const entries = Object.entries(prices).filter(([_, p]) => p > 0);

            let bestBuyVenue = '---';
            let bestBuyPrice = 0;

            if (entries.length > 0) {
                // Simplification for card: just show best price and a venue
                const best = entries.reduce((a, b) => a[1] > b[1] ? a : b); // Max price (Sell)
                bestBuyVenue = best[0].substring(0, 3);
                bestBuyPrice = best[1];
            }

            return `
                <div class="meme-card ${hotClass}" onclick="window.tradingOS.terminal.addLog('SNIPER', 'INFO', 'Selected ${token.symbol}')">
                    <div class="meme-card-top">
                        <span class="meme-symbol">$${token.symbol}</span>
                        <span class="meme-spread">+${spread.toFixed(2)}%</span>
                    </div>
                    <div class="meme-card-bottom">
                        <span class="meme-price">$${bestBuyPrice.toFixed(4)}</span>
                        <span class="meme-venue">${bestBuyVenue}</span>
                    </div>
                </div>
            `;
        }).join('');

        this.container.innerHTML = cardsHtml;
    }
}
