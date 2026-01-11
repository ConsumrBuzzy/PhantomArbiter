/**
 * TickerTape - Reusable Scrolling Marquee
 * ========================================
 * A standardized, mode-aware ticker component.
 * 
 * Features:
 * - Mode-aware styling (Red=Live, Purple=Paper)
 * - Intersection Observer (only animates when visible)
 * - Configurable speed and direction
 * - Whale Alert filter (> $50,000 transactions)
 * 
 * Instances:
 * - SolPriceTape: Real-time SOL/USDC price
 * - WhaleTape: Large on-chain transactions
 * - ArbSpreadTape: DEX spread opportunities
 * - FundingRateTape: Drift vs CEX funding rates
 */

export class TickerTape {
    /**
     * @param {string} containerId - DOM element ID to mount into
     * @param {Object} options - Configuration options
     * @param {string} options.mode - 'live' or 'paper' (affects glow color)
     * @param {number} options.speed - Animation speed in pixels/second (default: 50)
     * @param {string} options.direction - 'left' or 'right' (default: 'left')
     * @param {boolean} options.whaleFilter - Enable whale alert highlighting (default: false)
     * @param {number} options.whaleThreshold - USD threshold for whale alerts (default: 50000)
     */
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = {
            mode: options.mode || 'paper',
            speed: options.speed || 50,
            direction: options.direction || 'left',
            whaleFilter: options.whaleFilter || false,
            whaleThreshold: options.whaleThreshold || 50000,
            maxItems: options.maxItems || 20
        };

        this.items = [];
        this.isVisible = true;
        this.animationId = null;
        this.scrollPosition = 0;

        this._setupObserver();
        this.render();
    }

    /**
     * Setup Intersection Observer for performance
     * Only animate when ticker is visible on screen
     */
    _setupObserver() {
        if (!this.container || !('IntersectionObserver' in window)) return;

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                this.isVisible = entry.isIntersecting;
                if (this.isVisible) {
                    this._startAnimation();
                } else {
                    this._stopAnimation();
                }
            });
        }, { threshold: 0.1 });

        observer.observe(this.container);
    }

    /**
     * Render the tape container
     */
    render() {
        if (!this.container) return;

        const modeClass = this.options.mode === 'live' ? 'ticker-tape--live' : 'ticker-tape--paper';

        this.container.innerHTML = `
            <div class="ticker-tape ${modeClass}">
                <div class="ticker-track" id="${this.container.id}-track">
                    <div class="ticker-content">
                        <span class="ticker-placeholder">Loading...</span>
                    </div>
                </div>
            </div>
        `;

        this.track = document.getElementById(`${this.container.id}-track`);
        this._startAnimation();
    }

    /**
     * Set operating mode (affects visual styling)
     * @param {string} mode - 'live' or 'paper'
     */
    setMode(mode) {
        this.options.mode = mode;
        const tape = this.container?.querySelector('.ticker-tape');
        if (tape) {
            tape.classList.remove('ticker-tape--live', 'ticker-tape--paper');
            tape.classList.add(mode === 'live' ? 'ticker-tape--live' : 'ticker-tape--paper');
        }
    }

    /**
     * Update tape with new items
     * @param {Array} items - Array of ticker items
     * Each item: { text: string, type: string, value?: number, timestamp?: number }
     */
    update(items) {
        if (!Array.isArray(items)) {
            items = [items];
        }

        // Merge new items, keeping max limit
        items.forEach(item => {
            // Avoid duplicates by text
            const exists = this.items.find(i => i.text === item.text && i.timestamp === item.timestamp);
            if (!exists) {
                this.items.unshift(item);
            }
        });

        // Trim to max
        this.items = this.items.slice(0, this.options.maxItems);

        this._renderItems();
    }

    /**
     * Add a single item to the tape
     * @param {Object} item - Ticker item
     */
    addItem(item) {
        this.update([item]);
    }

    /**
     * Clear all items
     */
    clear() {
        this.items = [];
        this._renderItems();
    }

    /**
     * Render items into the track
     */
    _renderItems() {
        const content = this.container?.querySelector('.ticker-content');
        if (!content) return;

        if (this.items.length === 0) {
            content.innerHTML = '<span class="ticker-placeholder">Scanning for signals...</span>';
            return;
        }

        let html = '';
        this.items.forEach(item => {
            const isWhale = this.options.whaleFilter &&
                item.value &&
                item.value >= this.options.whaleThreshold;

            const typeClass = `ticker-item--${item.type || 'neutral'}`;
            const whaleClass = isWhale ? 'ticker-item--whale' : '';

            html += `
                <span class="ticker-item ${typeClass} ${whaleClass}">
                    ${isWhale ? '🐋 ' : ''}${item.text}
                </span>
                <span class="ticker-separator">•</span>
            `;
        });

        // Duplicate for seamless loop
        content.innerHTML = html + html;
    }

    /**
     * Start CSS animation
     */
    _startAnimation() {
        if (!this.track || this.animationId) return;

        const content = this.track.querySelector('.ticker-content');
        if (!content) return;

        // Calculate duration based on content width and speed
        const contentWidth = content.scrollWidth / 2; // Half because we duplicate
        const duration = contentWidth / this.options.speed;

        content.style.animationDuration = `${duration}s`;
        content.style.animationDirection = this.options.direction === 'right' ? 'reverse' : 'normal';
        content.classList.add('ticker-animate');
    }

    /**
     * Stop animation (when not visible)
     */
    _stopAnimation() {
        const content = this.container?.querySelector('.ticker-content');
        if (content) {
            content.classList.remove('ticker-animate');
        }
    }

    /**
     * Factory: Create a SolPrice Tape
     */
    static createSolPriceTape(containerId, mode = 'paper') {
        return new TickerTape(containerId, {
            mode,
            speed: 30,
            whaleFilter: false
        });
    }

    /**
     * Factory: Create a Whale Tape
     */
    static createWhaleTape(containerId, mode = 'paper') {
        return new TickerTape(containerId, {
            mode,
            speed: 40,
            whaleFilter: true,
            whaleThreshold: 50000
        });
    }

    /**
     * Factory: Create an Arb Spread Tape
     */
    static createArbSpreadTape(containerId, mode = 'paper') {
        return new TickerTape(containerId, {
            mode,
            speed: 35,
            whaleFilter: false
        });
    }

    /**
     * Factory: Create a Funding Rate Tape  
     */
    static createFundingRateTape(containerId, mode = 'paper') {
        return new TickerTape(containerId, {
            mode,
            speed: 25,
            whaleFilter: false
        });
    }
}

/**
 * Helper: Format USD value for tape display
 */
export function formatTapeValue(value) {
    if (value >= 1000000) {
        return '$' + (value / 1000000).toFixed(1) + 'M';
    }
    if (value >= 1000) {
        return '$' + (value / 1000).toFixed(1) + 'K';
    }
    return '$' + value.toFixed(2);
}

/**
 * Helper: Create tape item from price data
 */
export function createPriceItem(symbol, price, change) {
    const isPositive = change >= 0;
    return {
        text: `${symbol} ${formatTapeValue(price)} ${isPositive ? '▲' : '▼'}${Math.abs(change).toFixed(2)}%`,
        type: isPositive ? 'buy' : 'sell',
        value: price,
        timestamp: Date.now()
    };
}

/**
 * Helper: Create tape item from whale transaction
 */
export function createWhaleItem(symbol, amount, direction) {
    return {
        text: `${symbol} ${formatTapeValue(amount)} ${direction === 'buy' ? '🟢 BUY' : '🔴 SELL'}`,
        type: direction,
        value: amount,
        timestamp: Date.now()
    };
}
