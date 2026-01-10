/**
 * Market Data Component
 * =====================
 * Displays live market data (SOL price) in header.
 */

export class MarketData {
    constructor() {
        this.priceEl = document.getElementById('stats-sol-price');
        this.lastPrice = null;
    }

    /**
     * Update SOL price display
     */
    update(data) {
        if (!this.priceEl || !data.sol_price) return;

        const price = data.sol_price;
        this.priceEl.textContent = `$${price.toFixed(2)}`;

        // Flash effect on update
        this.priceEl.style.color = 'var(--neon-green)';
        setTimeout(() => {
            this.priceEl.style.color = 'var(--neon-blue)';
        }, 300);

        // Store for reference
        this.lastPrice = price;
    }

    /**
     * Get last known price
     */
    getPrice() {
        return this.lastPrice;
    }
}

export default MarketData;
