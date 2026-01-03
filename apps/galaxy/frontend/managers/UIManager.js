
export class UIManager {
    constructor() {
        this.labels = new Map(); // id -> HTMLElement

        // 1. Label Container (Full screen overlay)
        this.labelContainer = document.createElement('div');
        this.labelContainer.id = 'ui-layer-labels';
        Object.assign(this.labelContainer.style, {
            position: 'absolute',
            top: '0',
            left: '0',
            width: '100%',
            height: '100%',
            pointerEvents: 'none', // Allow clicks to pass through to canvas (unless hitting a pointer-events: auto child)
            zIndex: '10'
        });
        document.body.appendChild(this.labelContainer);

        // 2. Details Panel
        this.createDetailsPanel();
    }

    createDetailsPanel() {
        this.detailsPanel = document.createElement('div');
        this.detailsPanel.className = 'details-panel';
        this.detailsPanel.innerHTML = `
            <div class="details-close" onclick="this.parentElement.style.display='none'">X</div>
            <div class="details-header">
                <div class="details-title" id="dp-title">TOKEN</div>
                <div class="details-subtitle" id="dp-subtitle">SECTOR</div>
            </div>
            <div class="stat-grid">
                <div class="stat-box">
                    <div class="stat-label">Price</div>
                    <div class="stat-value" id="dp-price">$-</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">24h Change</div>
                    <div class="stat-value" id="dp-change" style="color: #0f0">+0.0%</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Market Cap</div>
                    <div class="stat-value" id="dp-mcap">$-</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Volume</div>
                    <div class="stat-value" id="dp-vol">$-</div>
                </div>
            </div>
        `;
        document.body.appendChild(this.detailsPanel);
    }

    // --- Label Management ---

    createLabel(id, text, params, onSelectCallback) {
        if (this.labels.has(id)) return this.labels.get(id);

        const rsi = params.rsi !== undefined ? params.rsi : 50;
        const details = this.formatPrice(params.price);

        const div = document.createElement('div');
        div.id = `label-${id}`;
        div.className = 'node-label';

        // Interaction
        div.onclick = (e) => {
            e.stopPropagation();
            if (onSelectCallback) onSelectCallback(id);
        };

        const rsiColor = rsi > 70 ? '#f00' : (rsi < 30 ? '#0f0' : '#fff');
        div.innerHTML = `
            <div class="label-content">
                <div class="label-title">${text}</div>
                <div class="label-details">${details}</div>
                <div class="label-rsi" style="color: ${rsiColor}">RSI: ${rsi.toFixed(0)}</div>
            </div>
        `;

        this.labelContainer.appendChild(div);
        this.labels.set(id, div);
        return div;
    }

    updateLabelPosition(id, x, y, z, distance) {
        const div = this.labels.get(id);
        if (!div) return;

        // Visibility / Occlusion Logic
        if (z > 1 || distance > 1500) {
            div.style.display = 'none';
        } else {
            div.style.display = 'block';
            div.style.opacity = Math.max(0, 1 - (distance / 1500));
            div.style.transform = `translate(-50%, -50%) translate(${x}px,${y}px)`;
        }
    }

    updateLabelData(id, params) {
        const div = this.labels.get(id);
        if (!div) return;

        // Start simple: re-render or update specific children
        // For performance, direct DOM update is better than innerHTML
        const detailsEl = div.querySelector('.label-details');
        if (detailsEl && params.price) detailsEl.innerText = this.formatPrice(params.price);

        const rsiEl = div.querySelector('.label-rsi');
        if (rsiEl && params.rsi !== undefined) {
            const rsi = params.rsi;
            const rsiColor = rsi > 70 ? '#f00' : (rsi < 30 ? '#0f0' : '#fff');
            rsiEl.innerText = `RSI: ${rsi.toFixed(0)}`;
            rsiEl.style.color = rsiColor;
        }
    }

    removeLabel(id) {
        const div = this.labels.get(id);
        if (div) {
            div.remove();
            this.labels.delete(id);
        }
    }

    // --- Details Panel ---

    showDetails(nodeData) {
        const p = nodeData.params;

        this.detailsPanel.style.display = 'block';

        document.getElementById('dp-title').innerText = nodeData.label;
        document.getElementById('dp-subtitle').innerText = p.category || 'UNKNOWN SECTOR';
        document.getElementById('dp-price').innerText = this.formatPrice(p.price);

        const change = p.change_24h || (Math.random() * 20 - 5);
        const changeEl = document.getElementById('dp-change');
        changeEl.innerText = `${change > 0 ? '+' : ''}${change.toFixed(2)}%`;
        changeEl.style.color = change >= 0 ? '#0f0' : '#f00';

        const mcap = p.market_cap || (Math.random() * 10000000);
        document.getElementById('dp-mcap').innerText = `$${(mcap / 1000000).toFixed(1)}M`;

        const vol = p.volume || (Math.random() * 500000);
        document.getElementById('dp-vol').innerText = `$${(vol / 1000).toFixed(1)}K`;
    }

    hideDetails() {
        this.detailsPanel.style.display = 'none';
    }

    // --- Helpers ---

    formatPrice(price) {
        // Mock fallback
        let val = price;
        if (!val || val === 0) {
            val = 0.001 + Math.random() * 0.01;
        }

        if (val < 0.000001) return `Val: $${val.toExponential(2)}`;
        if (val < 0.01) return `Val: $${val.toFixed(6)}`;
        return `Val: $${val.toFixed(2)}`;
    }
}
