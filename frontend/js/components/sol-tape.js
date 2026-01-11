/**
 * Sol Price Tape Component
 * Displays SOL price across multiple venues (Mocked from single feed for now)
 */
export class SolTape {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.basePrice = 0;
    }

    update(basePrice) {
        if (!this.container || !basePrice) return;
        this.basePrice = basePrice;
        this.render();
    }

    render() {
        // Mocking venue prices based on basePrice
        // In a real system, these would come from the backend's aggregate feed
        const venues = [
            { name: 'BINANCE', price: this.basePrice, color: '#FCD535' },
            { name: 'KRAKEN', price: this.basePrice * 1.0005, color: '#5741D9' },
            { name: 'RAYDIUM', price: this.basePrice * 0.9992, color: '#00D4FF' },
            { name: 'ORCA', price: this.basePrice * 1.0012, color: '#FFD700' },
            { name: 'METEORA', price: this.basePrice * 0.9998, color: '#FF00FF' },
            { name: 'JUPITER', price: this.basePrice * 1.0000, color: '#00FA9A' }
        ];

        // Duplicate for seamless infinite scroll
        const displayItems = [...venues, ...venues];

        const tickerHtml = displayItems.map(v => `
            <div class="sol-price-item">
                <span class="venue-tag" style="color:${v.color}; border:1px solid ${v.color}40">${v.name}</span>
                <span style="color:${v.price >= this.basePrice ? 'var(--neon-green)' : 'var(--neon-red)'}">
                    ${v.price.toFixed(2)}
                </span>
            </div>
        `).join('');

        // Apply to clean container or update existing
        // For tape, full replacement is easiest unless we want complex DOM recycling
        this.container.innerHTML = `<div class="sol-tape-ticker">${tickerHtml}</div>`;
    }
}
