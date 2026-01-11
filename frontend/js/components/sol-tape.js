/**
 * Sol Price Tape Component
 * Displays SOL price across multiple venues (Mocked from single feed for now)
 * 
 * FIX: Prices update in-place without resetting the CSS animation.
 */
export class SolTape {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.basePrice = 0;
        this.initialized = false;

        // Venue configuration (static - never changes)
        this.venues = [
            { name: 'BINANCE', multiplier: 1.0000, color: '#FCD535' },
            { name: 'KRAKEN', multiplier: 1.0005, color: '#5741D9' },
            { name: 'RAYDIUM', multiplier: 0.9992, color: '#00D4FF' },
            { name: 'ORCA', multiplier: 1.0012, color: '#FFD700' },
            { name: 'METEORA', multiplier: 0.9998, color: '#FF00FF' },
            { name: 'JUPITER', multiplier: 1.0000, color: '#00FA9A' }
        ];
    }

    update(basePrice) {
        if (!this.container || !basePrice) return;
        this.basePrice = basePrice;

        if (!this.initialized) {
            this.initializeTicker();
        } else {
            this.updatePricesInPlace();
        }
    }

    /**
     * One-time initialization of the ticker DOM structure.
     * Animation starts here and never resets.
     */
    initializeTicker() {
        // Duplicate for seamless infinite scroll
        const displayItems = [...this.venues, ...this.venues];

        const tickerHtml = displayItems.map((v, idx) => `
            <div class="sol-price-item">
                <span class="venue-tag" style="color:${v.color}; border:1px solid ${v.color}40">${v.name}</span>
                <span class="sol-price-value" data-venue-idx="${idx % this.venues.length}" 
                      style="color:var(--neon-green)">
                    ${(this.basePrice * v.multiplier).toFixed(2)}
                </span>
            </div>
        `).join('');

        this.container.innerHTML = `<div class="sol-tape-ticker">${tickerHtml}</div>`;
        this.initialized = true;
    }

    /**
     * Update only the price values without touching the DOM structure.
     * This prevents the CSS animation from resetting.
     */
    updatePricesInPlace() {
        const priceElements = this.container.querySelectorAll('.sol-price-value');

        priceElements.forEach(el => {
            const venueIdx = parseInt(el.dataset.venueIdx, 10);
            const venue = this.venues[venueIdx];
            const newPrice = this.basePrice * venue.multiplier;

            // Update price text
            el.textContent = newPrice.toFixed(2);

            // Update color based on spread from base
            el.style.color = venue.multiplier >= 1.0 ? 'var(--neon-green)' : 'var(--neon-red)';
        });
    }
}
