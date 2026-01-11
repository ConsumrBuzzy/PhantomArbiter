/**
 * Majors Tape Component
 * =====================
 * Displays real-time prices for major cryptos (BTC, ETH, SOL, etc.)
 * Uses the same scroll animation as SolTape but with different data sources.
 */
export class MajorsTape {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.initialized = false;

        // Major tokens to display
        this.majors = [
            { symbol: 'BTC', name: 'Bitcoin', color: '#F7931A', price: 0 },
            { symbol: 'ETH', name: 'Ethereum', color: '#627EEA', price: 0 },
            { symbol: 'SOL', name: 'Solana', color: '#00FFA3', price: 0 },
            { symbol: 'AVAX', name: 'Avalanche', color: '#E84142', price: 0 },
            { symbol: 'SUI', name: 'Sui', color: '#6FBCF0', price: 0 },
            { symbol: 'JUP', name: 'Jupiter', color: '#00D4AA', price: 0 }
        ];

        // Track price changes for color coding
        this.lastPrices = {};
    }

    /**
     * Update prices from price feed data
     * @param {Object} priceData - Object with symbol -> price mapping
     */
    update(priceData) {
        if (!this.container || !priceData) return;

        // Update internal prices
        let hasUpdates = false;
        this.majors.forEach(major => {
            const newPrice = priceData[major.symbol] || priceData[major.symbol.toLowerCase()];
            if (newPrice && newPrice > 0) {
                major.price = newPrice;
                hasUpdates = true;
            }
        });

        if (!hasUpdates) return;

        if (!this.initialized) {
            this.initializeTicker();
        } else {
            this.updatePricesInPlace();
        }
    }

    /**
     * One-time initialization of ticker DOM
     */
    initializeTicker() {
        // Only initialize if we have at least one price
        const hasPrice = this.majors.some(m => m.price > 0);
        if (!hasPrice) return;

        // Duplicate for seamless scroll
        const displayItems = [...this.majors, ...this.majors];

        const tickerHtml = displayItems.map((m, idx) => {
            const displayPrice = this.formatPrice(m.symbol, m.price);
            const change = this.getPriceChange(m.symbol, m.price);
            const changeClass = change >= 0 ? 'price-up' : 'price-down';
            const changeIcon = change >= 0 ? '▲' : '▼';

            return `
                <div class="majors-price-item">
                    <span class="majors-symbol" style="color:${m.color}">${m.symbol}</span>
                    <span class="majors-price" data-symbol="${m.symbol}" data-idx="${idx % this.majors.length}">${displayPrice}</span>
                    <span class="majors-change ${changeClass}">${changeIcon}</span>
                </div>
            `;
        }).join('');

        this.container.innerHTML = `<div class="majors-tape-ticker">${tickerHtml}</div>`;
        this.initialized = true;

        // Store last prices for change detection
        this.majors.forEach(m => {
            if (m.price > 0) this.lastPrices[m.symbol] = m.price;
        });
    }

    /**
     * Update prices without resetting animation
     */
    updatePricesInPlace() {
        const priceElements = this.container.querySelectorAll('.majors-price');

        priceElements.forEach(el => {
            const symbol = el.dataset.symbol;
            const major = this.majors.find(m => m.symbol === symbol);
            if (!major || major.price <= 0) return;

            const oldPrice = this.lastPrices[symbol] || 0;
            const newPrice = major.price;

            // Update text
            el.textContent = this.formatPrice(symbol, newPrice);

            // Update change indicator
            const changeEl = el.nextElementSibling;
            if (changeEl && changeEl.classList.contains('majors-change')) {
                if (newPrice > oldPrice) {
                    changeEl.textContent = '▲';
                    changeEl.className = 'majors-change price-up';
                } else if (newPrice < oldPrice) {
                    changeEl.textContent = '▼';
                    changeEl.className = 'majors-change price-down';
                }
            }
        });

        // Update last prices
        this.majors.forEach(m => {
            if (m.price > 0) this.lastPrices[m.symbol] = m.price;
        });
    }

    /**
     * Format price based on magnitude
     */
    formatPrice(symbol, price) {
        if (symbol === 'BTC') {
            return '$' + price.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
        } else if (price >= 100) {
            return '$' + price.toFixed(2);
        } else if (price >= 1) {
            return '$' + price.toFixed(2);
        } else {
            return '$' + price.toFixed(4);
        }
    }

    /**
     * Get price change direction
     */
    getPriceChange(symbol, currentPrice) {
        const lastPrice = this.lastPrices[symbol] || currentPrice;
        return currentPrice - lastPrice;
    }
}
