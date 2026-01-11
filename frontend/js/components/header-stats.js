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
        // Update Paper Wallet (Right) - use paper_wallet or fallback to wallet
        const paperData = stats.paper_wallet || stats.wallet;
        if (paperData) {
            this.updatePaperWallet(paperData);
        }

        // Update Live Wallet (Left) - use dedicated live_wallet data
        const liveData = stats.live_wallet;
        const liveEngine = stats.engines ? Object.values(stats.engines).find(e => e.live_mode && e.status === 'RUNNING') : null;
        this.updateLiveWallet(liveEngine, liveData);
    }

    updatePaperWallet(data) {
        if (this.paperEquity && data.equity !== undefined) {
            this.paperEquity.textContent = `$${data.equity.toFixed(2)}`;
        }
        if (this.paperSol && data.sol_balance !== undefined) {
            this.paperSol.textContent = data.sol_balance.toFixed(4);
        }
    }

    updateLiveWallet(liveEngine, liveData) {
        if (!this.liveContainer) return;

        const indicator = this.liveContainer.querySelector('.wallet-status-indicator');
        const hasLiveData = liveData && liveData.equity > 0;
        const isError = liveData && liveData.type && liveData.type.includes('error');

        if (hasLiveData) {
            // Display real Solana wallet balance
            this.liveContainer.style.opacity = '1';
            indicator.textContent = 'LIVE WALLET';

            if (this.liveBalance) {
                const equity = liveData.equity || 0;
                this.liveBalance.textContent = `$${equity.toFixed(2)}`;
                this.liveBalance.style.color = 'var(--neon-green)';
            }

            // Pulse if live engine running
            if (liveEngine) {
                indicator.classList.add('active');
            } else {
                indicator.classList.remove('active');
            }
        } else if (liveEngine) {
            // Live engine running but no wallet data yet
            this.liveContainer.style.opacity = '1';
            indicator.textContent = `LIVE: ${liveEngine.name.toUpperCase()}`;
            indicator.classList.add('active');
            if (this.liveBalance) this.liveBalance.textContent = "ACTIVE";
            this.liveBalance.style.color = "var(--neon-red)";
        } else if (isError) {
            // Error fetching live wallet
            this.liveContainer.style.opacity = '0.6';
            indicator.textContent = "LIVE WALLET";
            indicator.classList.remove('active');
            if (this.liveBalance) this.liveBalance.textContent = "ERROR";
            this.liveBalance.style.color = "var(--neon-red)";
        } else {
            // No live data or wallet not configured
            this.liveContainer.style.opacity = '0.6';
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
