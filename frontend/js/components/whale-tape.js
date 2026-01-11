/**
 * Whale Tape Component
 * ====================
 * Side-scrolling ticker for large market orders ("Whales").
 * Uses CSS animation for smooth scrolling.
 */

export class WhaleTape {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.items = [];

        // Mock initial data
        this.addTrade({ pair: 'SOL/USDC', side: 'buy', size: 125000 });
        this.addTrade({ pair: 'WIF/SOL', side: 'sell', size: 45000 });
        this.addTrade({ pair: 'BONK/USDC', side: 'buy', size: 80000 });

        // Simulate random whale activity for demo
        setInterval(() => this.simulateTrade(), 8000 + Math.random() * 5000);
    }

    simulateTrade() {
        const pairs = ['SOL/USDC', 'JUP/USDC', 'WIF/SOL', 'BONK/USDC', 'PYTH/USDC', 'RENDER/SOL'];
        const sides = ['buy', 'sell'];
        const pair = pairs[Math.floor(Math.random() * pairs.length)];
        const side = sides[Math.floor(Math.random() * sides.length)];
        const size = 50000 + Math.floor(Math.random() * 200000);

        this.addTrade({ pair, side, size });
    }

    addTrade(trade) {
        if (!this.container) return;

        const item = document.createElement('span');
        item.className = `tape-item item-${trade.side}`;
        item.title = `Whale Alert: Large ${trade.side.toUpperCase()} order detected on ${trade.pair}`;

        // Format size: $100k
        const sizeStr = `$${(trade.size / 1000).toFixed(0)}k`;
        const icon = trade.side === 'buy' ? '🟢' : '🔴';

        item.textContent = `${trade.pair} ${sizeStr} ${icon}`;

        this.container.appendChild(item);

        // Keep tape manageable (max 20 items in DOM)
        if (this.container.children.length > 20) {
            this.container.removeChild(this.container.firstChild);
        }
    }
}
