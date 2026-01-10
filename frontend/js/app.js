/**
 * Phantom Arbiter - Dashboard Control Logic
 * V20: Reactive WebSocket Client
 */

class DashboardApp {
    constructor() {
        this.ws = null;
        this.maxLogs = 50;
        this.logStream = document.getElementById('log-stream');
        this.intelTableBody = document.querySelector('#intel-table tbody');
        this.inventoryTableBody = document.querySelector('#inventory-table tbody');

        // Stats Elements
        this.engineMode = document.getElementById('engine-mode');
        this.statsLatency = document.getElementById('stats-latency');
        this.statsPnl = document.getElementById('stats-pnl');

        this.connect();
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname || 'localhost';
        const port = 8765;
        const url = `${protocol}//${host}:${port}`;

        this.addLog('SYSTEM', 'INFO', `Attempting Link to ${url}...`);

        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            this.addLog('SYSTEM', 'SUCCESS', 'Neural Link Established');
            this.engineMode.textContent = 'LINKED';
            this.engineMode.style.color = 'var(--neon-green)';
        };

        this.ws.onmessage = (event) => {
            try {
                const packet = JSON.parse(event.data);
                this.handlePacket(packet);
            } catch (e) {
                console.error("Parse error", e);
            }
        };

        this.ws.onclose = () => {
            this.addLog('SYSTEM', 'WARNING', 'Link Closed - Retrying in 3s...');
            this.engineMode.textContent = 'OFFLINE';
            this.engineMode.style.color = 'var(--neon-red)';
            setTimeout(() => this.connect(), 3000);
        };

        this.ws.onerror = (err) => {
            this.addLog('SYSTEM', 'ERROR', 'WebSocket Connection Error');
        };
    }

    handlePacket(packet) {
        const { type, data } = packet;

        switch (type) {
            case 'SYSTEM_STATS':
                this.updateStats(data);
                break;
            case 'LOG_ENTRY':
                this.addLog(data.source, data.level, data.message, data.timestamp);
                break;
            case 'ARB_OPP':
                this.updateIntelTable('ARB', data);
                break;
            case 'SCALP_SIGNAL':
                this.updateIntelTable('SCALP', data);
                break;
            case 'INVENTORY_UPDATE':
                this.updateInventory(data);
                break;
            default:
            // console.log("Unhandled packet type:", type, data);
        }
    }

    updateStats(stats) {
        if (stats.mode) this.engineMode.textContent = stats.mode.toUpperCase();
        if (stats.wss_latency_ms !== undefined) this.statsLatency.textContent = `${stats.wss_latency_ms}ms`;
        if (stats.settled_pnl !== undefined) {
            const val = stats.settled_pnl;
            this.statsPnl.textContent = `$${val.toFixed(2)}`;
            this.statsPnl.style.color = val >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
        }
    }

    updateIntelTable(mode, item) {
        // Clear "Waiting..." if present
        if (this.intelTableBody.innerText.includes('Listening')) {
            this.intelTableBody.innerHTML = '';
        }

        const row = document.createElement('tr');

        if (mode === 'ARB') {
            const profitColor = item.profit_pct > 0 ? 'var(--neon-green)' : 'white';
            row.innerHTML = `
                <td>${item.token}</td>
                <td style="font-size: 0.7rem; color: var(--text-dim);">${item.route}</td>
                <td style="color: ${profitColor}">${item.profit_pct.toFixed(2)}%</td>
                <td>$${item.est_profit_sol.toFixed(2)}</td>
            `;
        } else if (mode === 'SCALP') {
            const actionColor = item.action === 'BUY' ? 'var(--neon-green)' : 'var(--neon-red)';
            row.innerHTML = `
                <td>${item.token}</td>
                <td>${item.signal}</td>
                <td style="color: ${actionColor}; font-weight: bold;">${item.action}</td>
                <td>${(item.confidence * 100).toFixed(0)}%</td>
            `;
        }

        this.intelTableBody.prepend(row);

        // Limit rows to 15
        if (this.intelTableBody.children.length > 15) {
            this.intelTableBody.removeChild(this.intelTableBody.lastChild);
        }
    }

    updateInventory(items) {
        this.inventoryTableBody.innerHTML = '';
        items.forEach(item => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${item.symbol}</td>
                <td style="text-align: right;">${item.amount.toFixed(3)}</td>
                <td style="text-align: right;">$${item.value_usd.toFixed(2)}</td>
            `;
            this.inventoryTableBody.appendChild(row);
        });
    }

    addLog(source, level, message, timestamp) {
        const time = timestamp ? new Date(timestamp * 1000).toLocaleTimeString() : new Date().toLocaleTimeString();
        const entry = document.createElement('div');
        entry.className = `log-entry ${level}`;
        entry.innerHTML = `<span style="color: var(--text-dim); font-size: 0.7rem;">[${time}]</span> <span style="font-weight: bold;">[${source}]</span> ${message}`;

        this.logStream.prepend(entry);

        // Throttling
        if (this.logStream.children.length > this.maxLogs) {
            this.logStream.removeChild(this.logStream.lastChild);
        }
    }
}

// Global Init
window.addEventListener('load', () => {
    window.app = new DashboardApp();
});
