/**
 * Meme Sniper Strip Component
 * ===========================
 * Displays high-velocity meme token opportunities in the header.
 * Horizontal scrolling strip of "hot cards".
 */

export class MemeSniperStrip {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.tokenMap = new Map(); // Stores full token state: symbol -> tokenObj
        this.STORAGE_KEY = 'meme_sniper_data_v1';
        this._loadFromStorage();
    }

    _loadFromStorage() {
        try {
            const saved = localStorage.getItem(this.STORAGE_KEY);
            if (saved) {
                const parsed = JSON.parse(saved);
                if (Array.isArray(parsed)) {
                    parsed.forEach(item => {
                        if (item && item.symbol) {
                            this.tokenMap.set(item.symbol, item);
                        }
                    });
                    // Initial render from cache
                    console.log(`[MemeSniper] Loaded ${this.tokenMap.size} tokens from cache`);
                    this._renderMap();
                }
            }
        } catch (e) {
            console.warn('[MemeSniper] Failed to load cache', e);
        }
    }

    _saveToStorage() {
        try {
            const data = Array.from(this.tokenMap.values());
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(data));
        } catch (e) {
            // Ignore quota errors
        }
    }

    /**
     * Update with token watchlist data
     * @param {Object} data - Contains 'tokens' array (from TOKEN_WATCHLIST packet)
     */
    update(data) {
        if (!this.container) return;

        // Handle empty updates gracefully
        const incomingTokens = data.tokens || [];

        // 1. Process Data & Update Persistence Map
        incomingTokens.forEach(token => {
            const symbol = token.symbol;
            const currentPrice = this._getBestPrice(token);

            // Get existing or init new record
            let existing = this.tokenMap.get(symbol) || {
                ...token,
                lastPrice: currentPrice,
                trend: 'FLAT',
                trendStartTime: Date.now()
            };

            // Detect Trend Change
            if (currentPrice > existing.lastPrice) {
                if (existing.trend !== 'UP') {
                    existing.trend = 'UP';
                    existing.trendStartTime = Date.now();
                }
            } else if (currentPrice < existing.lastPrice) {
                if (existing.trend !== 'DOWN') {
                    existing.trend = 'DOWN';
                    existing.trendStartTime = Date.now();
                }
            }

            // Update the record with latest data (prices, volume, etc)
            // But preserve our calculated trend/lastPrice state
            const updatedRecord = {
                ...existing,       // Keep prev state
                ...token,          // Overwrite with new API data
                lastPrice: currentPrice,
                trend: existing.trend,
                trendStartTime: existing.trendStartTime,
                currentPrice: currentPrice // Add currentPrice for rendering
            };

            this.tokenMap.set(symbol, updatedRecord);
        });

        this._saveToStorage();
        this._renderMap();
    }

    _getBestPrice(token) {
        const prices = token.prices || {};
        const entries = Object.entries(prices).filter(([_, p]) => p > 0);
        if (entries.length === 0) return 0;
        // Max price (Sell side proxy)
        return entries.reduce((a, b) => a[1] > b[1] ? a : b)[1];
    }

    /**
     * Internal render logic using persistent map
     */
    _renderMap() {
        const allTokens = Array.from(this.tokenMap.values());

        // Sort by spread descending
        const hotTokens = allTokens
            .sort((a, b) => (b.spread_pct || 0) - (a.spread_pct || 0))
            .slice(0, 50); // Show top 50 "Active" tokens

        // Only show loading if we TRULY have no data ever
        if (hotTokens.length === 0) {
            if (!this.container.querySelector('.sniper-loading')) {
                this.container.innerHTML = '<div class="sniper-loading">Scanning Mempool...</div>';
            }
            return;
        }

        const cardsHtml = hotTokens.map(token => {
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
                        <span class="meme-price">$${(token.currentPrice || 0).toFixed(4)}</span>
                        <span class="meme-spread ${spread > 0 ? 'positive' : ''}">+${spread.toFixed(2)}%</span>
                    </div>
                </div>
            `;
        }).join('');

        this.container.innerHTML = cardsHtml;
    }

    // Retain public render for compatibility if needed, but alias to _renderMap
    render(tokens) {
        // Legacy call - ignore tokens argument and use internal map to be safe
        this._renderMap();
    }
}
