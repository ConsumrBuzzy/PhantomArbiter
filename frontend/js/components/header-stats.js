/**
 * Header Stats Component
 * ======================
 * Manages the header status bar display, including Global Mode and Wallet.
 */

/**
 * Header Stats Component
 * ======================
 * Manages the split header display: Live Wallet (Left) and Paper Wallet (Right).
 */

export class HeaderStats {
    constructor() {
        // Live Wallet (Left)
        this.liveContainer = document.getElementById('live-wallet-display');
        this.liveBalance = document.getElementById('live-wallet-balance');

        // Paper Wallet (Right)
        this.paperContainer = document.getElementById('paper-wallet-display');
        this.paperEquity = document.getElementById('wallet-balance');
        this.paperSol = document.getElementById('wallet-sol');
    }

    /**
     * Update system stats
     */
    update(stats) {
        // Update Paper Wallet (Right)
        if (stats.wallet) {
            this.updatePaperWallet(stats.wallet);
        }

        // Update Live Wallet (Left)
        // Check if any engine is running in LIVE mode to populate this
        if (stats.engines) {
            const liveEngine = Object.values(stats.engines).find(e => e.live_mode && e.status === 'RUNNING');
            this.updateLiveWallet(liveEngine, stats.wallet); // passing global wallet for now, ideally needs live wallet data
        }
    }

    updatePaperWallet(data) {
        if (this.paperEquity && data.equity !== undefined) {
            this.paperEquity.textContent = `$${data.equity.toFixed(2)}`;
        }
        if (this.paperSol && data.sol_balance !== undefined) {
            this.paperSol.textContent = data.sol_balance.toFixed(4);
        }
    }

    updateLiveWallet(liveEngine, walletData) {
        if (!this.liveContainer) return;

        const indicator = this.liveContainer.querySelector('.wallet-status-indicator');
        const isLiveWallet = walletData && walletData.type && walletData.type.startsWith('LIVE');

        if (isLiveWallet || liveEngine) {
            // Active Live Wallet or Live Engine Running
            this.liveContainer.style.opacity = '1';

            if (isLiveWallet) {
                // Display actual live wallet balance
                indicator.textContent = 'LIVE WALLET';
                if (this.liveBalance) {
                    const equity = walletData.equity || 0;
                    this.liveBalance.textContent = `$${equity.toFixed(2)}`;
                    this.liveBalance.style.color = equity > 0 ? 'var(--neon-green)' : 'var(--text-dim)';
                }
            } else if (liveEngine) {
                // Live engine running but wallet not in LIVE mode
                indicator.textContent = `LIVE: ${liveEngine.name.toUpperCase()}`;
                indicator.classList.add('active');
                if (this.liveBalance) this.liveBalance.textContent = "ACTIVE";
                this.liveBalance.style.color = "var(--neon-red)";
            }

            // Trigger pulse if live engine is running
            if (liveEngine) {
                indicator.classList.add('active');
            } else {
                indicator.classList.remove('active');
            }
        } else {
            // No Live Data - Show dimmed state
            this.liveContainer.style.opacity = '0.5';
            indicator.textContent = "LIVE WALLET";
            indicator.classList.remove('active');
            if (this.liveBalance) this.liveBalance.textContent = "$0.00";
            this.liveBalance.style.color = "var(--text-dim)";
        }
    }

    // Methods for Pulse/Context removed as UI elements were removed.
    updateContext(data) {
        // No-op or reimplement if we add pulse bubbles back elsewhere
    }

    setEngineCount(running, total) {
        // No-op
    }

    setConnectionStatus(connected) {
        // Could update logo or add a status dot later
    }
}

export default HeaderStats;
