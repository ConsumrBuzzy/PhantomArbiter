/**
 * Header Stats Component
 * ======================
 * V23.0: Streamlined - Wallet displays removed from header.
 * Balance data is now shown exclusively in the Universal Vault component.
 * 
 * This class is kept as a safe no-op stub for backward compatibility.
 */

export class HeaderStats {
    constructor() {
        // Legacy element references (now removed from DOM)
        // Kept as no-ops for backward compatibility with app.module.js
        this.liveContainer = null;
        this.liveBalance = null;
        this.paperEquity = null;
        this.paperSol = null;
    }

    /**
     * Update system stats (no-op - data handled by UnifiedVault)
     */
    update(stats) {
        // All wallet balance display is now handled by UnifiedVaultController
        // This method is kept for backward compatibility
    }

    updatePaperWallet(data) {
        // No-op: Paper wallet display removed from header
    }

    updateLiveWallet(liveEngine, liveData) {
        // No-op: Live wallet display removed from header
    }

    updateContext(data) {
        // No-op
    }

    setEngineCount(running, total) {
        // No-op
    }

    setConnectionStatus(connected) {
        // Could add a small status dot to the header brand in the future
    }
}

export default HeaderStats;

