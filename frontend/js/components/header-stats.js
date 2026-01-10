/**
 * Header Stats Component
 * ======================
 * Manages the header status bar display, including Global Mode and Wallet.
 */

export class HeaderStats {
    constructor() {
        this.engineMode = document.getElementById('engine-mode');
        this.statsLatency = document.getElementById('stats-latency');
        this.statsPnl = document.getElementById('stats-pnl');
        this.statsEngines = document.getElementById('stats-engines');

        // New Wallet Components
        this.walletBalance = document.getElementById('wallet-balance');
        this.walletSol = document.getElementById('wallet-sol');
        this.modeDisplay = document.getElementById('global-mode-display');
        this.modeToggle = document.getElementById('global-mode-toggle');

        // Market Pulse Components
        this.pulseSolBtc = document.getElementById('pulse-sol-btc');
        this.pulseJito = document.getElementById('pulse-jito');

        this.onModeToggle = null;

        this.bindEvents();
    }

    bindEvents() {
        if (this.modeToggle) {
            this.modeToggle.addEventListener('change', (e) => {
                const mode = e.target.checked ? 'LIVE' : 'PAPER';
                this.updateModeDisplay(mode);
                if (this.onModeToggle) {
                    this.onModeToggle(mode);
                }
            });
        }
    }

    /**
     * Update Global Mode Display
     */
    updateModeDisplay(mode) {
        if (!this.modeDisplay) return;

        this.modeDisplay.textContent = mode;
        if (mode === 'LIVE') {
            this.modeDisplay.style.color = 'var(--neon-red)';
            this.modeDisplay.style.borderColor = 'var(--neon-red)';
            this.modeDisplay.style.boxShadow = '0 0 10px rgba(255, 0, 50, 0.3)';
        } else {
            this.modeDisplay.style.color = 'var(--text-dim)';
            this.modeDisplay.style.borderColor = 'var(--border-color)';
            this.modeDisplay.style.boxShadow = 'none';
        }
    }

    /**
     * Update Wallet Balance
     */
    updateWallet(data) {
        if (this.walletBalance && data.equity !== undefined) {
            this.walletBalance.textContent = `$${data.equity.toFixed(2)}`;
        }
        if (this.walletSol && data.sol_balance !== undefined) {
            this.walletSol.textContent = data.sol_balance.toFixed(4);
        }
    }

    /**
     * Update Market Pulse context
     */
    updateContext(data) {
        if (this.pulseSolBtc && data.sol_btc_strength) {
            this.pulseSolBtc.textContent = data.sol_btc_strength.toFixed(4);
        }

        if (this.pulseJito && data.jito_tip !== undefined) {
            const tip = data.jito_tip || 0;
            this.pulseJito.textContent = tip < 0.001 ? `${(tip * 1000000).toFixed(0)}µ` : `${tip.toFixed(4)}`;
        }

        if (data.rpc_latencies && data.rpc_latencies['Mainnet'] && this.statsLatency) {
            const ms = data.rpc_latencies['Mainnet'];
            this.statsLatency.textContent = `${ms}ms`;
            this.statsLatency.style.color = ms > 500 ? 'var(--neon-red)' : 'var(--neon-green)';
        }
    }

    /**
     * Update system stats
     */
    update(stats) {
        // The original `stats.mode` handling is removed as it's replaced by `global-mode-display` and `global-mode-toggle`.
        // if (stats.mode) {
        //     const mode = stats.mode.toUpperCase();
        //     if (this.engineMode) {
        //         this.engineMode.textContent = mode;
        //     }
        // }

        if (stats.wallet) {
            this.updateWallet(stats.wallet);
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
