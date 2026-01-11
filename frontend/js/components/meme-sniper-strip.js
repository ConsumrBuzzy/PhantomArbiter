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
        this.history = new Map(); // Stores { symbol: { lastPrice, trend, trendStartTime } }
    }

    /**
     * Update with token watchlist data
     * @param {Object} data - Contains 'tokens' array (from TOKEN_WATCHLIST packet)
     */
    update(data) {
        if (!this.container || !data.tokens) return;

        // 1. Process Data & Update History
        const processedTokens = data.tokens.map(token => {
            const symbol = token.symbol;
            const currentPrice = this._getBestPrice(token);

            let record = this.history.get(symbol) || {
                lastPrice: currentPrice,
                trend: 'FLAT',
                trendStartTime: Date.now()
            };

            // Detect Trend Change
            if (currentPrice > record.lastPrice) {
                if (record.trend !== 'UP') {
                    record.trend = 'UP';
                    record.trendStartTime = Date.now();
                }
            } else if (currentPrice < record.lastPrice) {
                if (record.trend !== 'DOWN') {
                    record.trend = 'DOWN';
                    record.trendStartTime = Date.now();
                }
            }

            record.lastPrice = currentPrice;
            this.history.set(symbol, record);

            return { ...token, ...record, currentPrice };
        });

        // 2. Filter & Sort (Hot Tokens)
        // Sort by spread descending
        const hotTokens = processedTokens
            .sort((a, b) => (b.spread_pct || 0) - (a.spread_pct || 0))
            .slice(0, 50); // Show top 50

        // If no tokens yet, keep loading or show empty state
        if (hotTokens.length === 0) {
            if (!this.container.querySelector('.sniper-loading')) {
                this.container.innerHTML = '<div class="sniper-loading">Scanning Mempool...</div>';
            }
            return;
        }

        this.render(hotTokens);
    }

    _getBestPrice(token) {
        const prices = token.prices || {};
        const entries = Object.entries(prices).filter(([_, p]) => p > 0);
        if (entries.length === 0) return 0;
        // Max price (Sell side proxy)
        return entries.reduce((a, b) => a[1] > b[1] ? a : b)[1];
    }

    render(tokens) {
        const cardsHtml = tokens.map(token => {
            const spread = token.spread_pct || 0;
            const isHot = spread > 1.0;
            const hotClass = isHot ? 'hot' : '';

            // Trend Visuals
            const isUp = token.trend === 'UP';
            const isDown = token.trend === 'DOWN';
            const trendIcon = isUp ? '▲' : (isDown ? '▼' : '•');
            const trendClass = isUp ? 'trend-up' : (isDown ? 'trend-down' : 'trend-flat');

            // Duration
            const durationSec = Math.floor((Date.now() - token.trendStartTime) / 1000);
            const durationStr = durationSec > 60 ? `${Math.floor(durationSec / 60)}m` : `${durationSec}s`;

            // Venue Logic
            const prices = token.prices || {};
            const entries = Object.entries(prices).filter(([_, p]) => p > 0);
            let bestBuyVenue = '---';

            if (entries.length > 0) {
                const best = entries.reduce((a, b) => a[1] > b[1] ? a : b);
                bestBuyVenue = best[0].substring(0, 3);
            }

            return `
                <div class="meme-card ${hotClass}" onclick="window.tradingOS.terminal.addLog('SNIPER', 'INFO', 'Selected ${token.symbol}')">
                    <div class="meme-card-top">
                        <span class="meme-symbol">$${token.symbol}</span>
                        <div class="meme-trend-badge ${trendClass}">
                            <span class="trend-icon">${trendIcon}</span>
                            <span class="trend-duration">${durationStr}</span>
                        </div>
                    </div>
                    <div class="meme-card-bottom">
                        <span class="meme-price">$${token.currentPrice.toFixed(4)}</span>
                        <span class="meme-spread ${spread > 0 ? 'positive' : ''}">+${spread.toFixed(2)}%</span>
                    </div>
                </div>
            `;
        }).join('');

        this.container.innerHTML = cardsHtml;
    }
}
