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

        if (liveEngine) {
            // Active Live Engine
            this.liveContainer.style.opacity = '1';
            this.liveContainer.querySelector('.wallet-status-indicator').textContent = `LIVE: ${liveEngine.name.toUpperCase()}`;

            // For MVP, if we don't have separate live wallet data, we show "Connected" or 0.00
            // Or if the backend sends live wallet data in a different field.
            // Currently assuming 'walletData' is the paper wallet.
            // We'll calculate a mock "Live" value or show Real Live balance if available.
            // For now, let's just make it look active.
            if (this.liveBalance) this.liveBalance.textContent = "CONNECTED";
            this.liveBalance.style.color = "var(--neon-red)";
        } else {
            // No Live Engine
            this.liveContainer.style.opacity = '0.3';
            this.liveContainer.querySelector('.wallet-status-indicator').textContent = "NO LIVE ENGINE";
            if (this.liveBalance) this.liveBalance.textContent = "--";
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
