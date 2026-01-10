/**
 * Header Stats Component
 * ======================
 * Manages the header status bar display.
 */

export class HeaderStats {
    constructor() {
        this.engineMode = document.getElementById('engine-mode');
        this.statsLatency = document.getElementById('stats-latency');
        this.statsPnl = document.getElementById('stats-pnl');
        this.statsEngines = document.getElementById('stats-engines');
    }

    /**
     * Update system stats
     */
    update(stats) {
        if (stats.mode) {
            const mode = stats.mode.toUpperCase();
            if (this.engineMode) {
                this.engineMode.textContent = mode;
            }
        }

        if (stats.wss_latency_ms !== undefined && this.statsLatency) {
            this.statsLatency.textContent = `${stats.wss_latency_ms}ms`;
        }

        if (stats.settled_pnl !== undefined && this.statsPnl) {
            const val = stats.settled_pnl;
            this.statsPnl.textContent = `$${val.toFixed(2)}`;
            this.statsPnl.style.color = val >= 0 ? 'var(--neon-green)' : 'var(--neon-red)';
        }
    }

    /**
     * Update engine count display
     */
    setEngineCount(running, total) {
        if (this.statsEngines) {
            this.statsEngines.textContent = `${running}/${total}`;
        }
    }

    /**
     * Set connection status
     */
    setConnectionStatus(connected) {
        if (this.engineMode) {
            if (connected) {
                this.engineMode.textContent = 'LINKED';
                this.engineMode.style.color = 'var(--neon-green)';
            } else {
                this.engineMode.textContent = 'OFFLINE';
                this.engineMode.style.color = 'var(--neon-red)';
            }
        }
    }
}

export default HeaderStats;
