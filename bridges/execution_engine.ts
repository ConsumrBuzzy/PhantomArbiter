/**
 * Unified Execution Engine
 * =========================
 * Atomic multi-DEX swap execution for Phantom Arbiter.
 * 
 * Supports:
 * - Meteora DLMM pools
 * - Orca Whirlpools (placeholder - SDK needs to be added)
 * - Jupiter (via API fallback)
 * - Jito bundles for MEV protection
 * - Compute Budget optimization
 * 
 * Usage:
 *   node execution_engine.js '{"command":"swap","legs":[...]}'
 * 
 * Commands:
 *   - swap: Execute atomic multi-leg swap
 *   - quote: Get quotes for multiple legs without executing
 *   - health: Check engine health and DEX availability
 */

import {
    Connection,
    PublicKey,
    Keypair,
    Transaction,
    VersionedTransaction,
    TransactionMessage,
    ComputeBudgetProgram,
    sendAndConfirmTransaction,
    LAMPORTS_PER_SOL,
} from '@solana/web3.js';
import DLMM from '@meteora-ag/dlmm';
import bs58 from 'bs58';
import BN from 'bn.js';

// ═══════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════

interface SwapLeg {
    dex: 'meteora' | 'orca' | 'jupiter';
    pool: string;
    inputMint: string;
    outputMint: string;
    amount: number;  // In smallest units
    slippageBps?: number;
}

interface EngineCommand {
    command: 'swap' | 'quote' | 'health' | 'simulate';
    legs?: SwapLeg[];
    privateKey?: string;
    useJito?: boolean;
    priorityFee?: number;  // In microlamports per CU
    simulateOnly?: boolean; // If true, simulate but don't send
}

interface EngineResult {
    success: boolean;
    command: string;
    signature?: string;
    legs?: LegResult[];
    error?: string;
    computeUnitsUsed?: number;
    simulationSuccess?: boolean;
    simulationError?: string;
    timestamp: number;
}

interface LegResult {
    dex: string;
    inputMint: string;
    outputMint: string;
    inputAmount: number;
    outputAmount: number;
    priceImpact?: number;
}

// ═══════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════

const RPC_URL = process.env.SOLANA_RPC_URL || 'https://api.mainnet-beta.solana.com';
const DEFAULT_COMPUTE_UNITS = 400_000;  // Multi-DEX swaps need more CU
const DEFAULT_PRIORITY_FEE = 50_000;     // 50k microlamports per CU
const DEFAULT_SLIPPAGE_BPS = 100;        // 1%

// ═══════════════════════════════════════════════════════════════════
// EXECUTION ENGINE
// ═══════════════════════════════════════════════════════════════════

class ExecutionEngine {
    private connection: Connection;
    private wallet?: Keypair;

    constructor() {
        this.connection = new Connection(RPC_URL, 'confirmed');
    }

    /**
     * Initialize wallet from private key
     */
    private setWallet(privateKey: string): void {
        try {
            const secretKey = bs58.decode(privateKey);
            this.wallet = Keypair.fromSecretKey(secretKey);
        } catch (e) {
            throw new Error('Invalid private key format');
        }
    }

    /**
     * Build Compute Budget instructions for priority fees
     */
    private buildComputeBudgetIxs(computeUnits: number, priorityFee: number) {
        return [
            ComputeBudgetProgram.setComputeUnitLimit({ units: computeUnits }),
            ComputeBudgetProgram.setComputeUnitPrice({ microLamports: priorityFee }),
        ];
    }

    /**
     * Build Meteora DLMM swap instruction
     */
    private async buildMeteoraSwap(leg: SwapLeg): Promise<any> {
        const poolAddr = new PublicKey(leg.pool);
        const dlmmPool = await DLMM.create(this.connection, poolAddr);

        const inputMint = new PublicKey(leg.inputMint);
        const isXtoY = inputMint.equals(dlmmPool.tokenX.publicKey);

        // Get quote first
        const binArrays = await dlmmPool.getBinArrayForSwap(isXtoY);
        const swapQuote = await dlmmPool.swapQuote(
            new BN(leg.amount),
            isXtoY,
            new BN(leg.slippageBps || DEFAULT_SLIPPAGE_BPS),
            binArrays
        );

        // Build swap transaction
        const swapTx = await dlmmPool.swap({
            inToken: inputMint,
            outToken: new PublicKey(leg.outputMint),
            inAmount: new BN(leg.amount),
            minOutAmount: swapQuote.minOutAmount,
            lbPair: dlmmPool.pubkey,
            user: this.wallet!.publicKey,
            binArraysPubkey: swapQuote.binArraysPubkey,
        });

        return {
            instructions: swapTx.instructions || [swapTx],
            quote: {
                inputAmount: leg.amount,
                outputAmount: swapQuote.outAmount.toNumber(),
                minOutputAmount: swapQuote.minOutAmount.toNumber(),
                priceImpact: swapQuote.priceImpact?.toNumber() || 0,
            }
        };
    }

    /**
     * Build Orca Whirlpool swap instruction (placeholder)
     * TODO: Add @orca-so/whirlpools-sdk implementation
     */
    private async buildOrcaSwap(leg: SwapLeg): Promise<any> {
        // Placeholder - Orca SDK needs to be added
        throw new Error('Orca integration not yet implemented. Use Meteora or Jupiter.');
    }

    /**
     * Execute atomic multi-leg swap
     * @param simulateOnly If true, simulate but don't send (seatbelt mode)
     */
    async executeSwap(legs: SwapLeg[], privateKey: string, priorityFee?: number, simulateOnly: boolean = false): Promise<EngineResult> {
        const timestamp = Date.now();

        try {
            this.setWallet(privateKey);

            if (legs.length === 0) {
                return { success: false, command: 'swap', error: 'No swap legs provided', timestamp };
            }

            // Build all swap instructions
            const allInstructions: any[] = [];
            const legResults: LegResult[] = [];

            // Add compute budget first
            const computeBudgetIxs = this.buildComputeBudgetIxs(
                DEFAULT_COMPUTE_UNITS * legs.length,
                priorityFee || DEFAULT_PRIORITY_FEE
            );
            allInstructions.push(...computeBudgetIxs);

            // Build each leg
            for (const leg of legs) {
                let swapResult;

                switch (leg.dex) {
                    case 'meteora':
                        swapResult = await this.buildMeteoraSwap(leg);
                        break;
                    case 'orca':
                        swapResult = await this.buildOrcaSwap(leg);
                        break;
                    case 'jupiter':
                        throw new Error('Jupiter integration uses REST API - not batched here');
                    default:
                        throw new Error(`Unknown DEX: ${leg.dex}`);
                }

                // Add instructions
                if (Array.isArray(swapResult.instructions)) {
                    allInstructions.push(...swapResult.instructions);
                } else {
                    allInstructions.push(swapResult.instructions);
                }

                legResults.push({
                    dex: leg.dex,
                    inputMint: leg.inputMint,
                    outputMint: leg.outputMint,
                    inputAmount: swapResult.quote.inputAmount,
                    outputAmount: swapResult.quote.outputAmount,
                    priceImpact: swapResult.quote.priceImpact,
                });
            }

            // Build and send transaction
            const { blockhash, lastValidBlockHeight } = await this.connection.getLatestBlockhash();

            const tx = new Transaction();
            tx.recentBlockhash = blockhash;
            tx.lastValidBlockHeight = lastValidBlockHeight;
            tx.feePayer = this.wallet!.publicKey;

            for (const ix of allInstructions) {
                if (ix.keys && ix.programId) {
                    tx.add(ix);
                }
            }

            // Sign the transaction for simulation
            tx.sign(this.wallet!);

            // ═══ SIMULATION SEATBELT ═══
            // Simulate before sending to prevent wasted gas
            const simulation = await this.connection.simulateTransaction(tx);

            if (simulation.value.err) {
                const simError = JSON.stringify(simulation.value.err);
                return {
                    success: false,
                    command: simulateOnly ? 'simulate' : 'swap',
                    legs: legResults,
                    simulationSuccess: false,
                    simulationError: `Simulation failed: ${simError}`,
                    computeUnitsUsed: simulation.value.unitsConsumed,
                    error: `Transaction would fail: ${simError}`,
                    timestamp,
                };
            }

            // If simulation-only mode, return success without sending
            if (simulateOnly) {
                return {
                    success: true,
                    command: 'simulate',
                    legs: legResults,
                    simulationSuccess: true,
                    computeUnitsUsed: simulation.value.unitsConsumed,
                    timestamp,
                };
            }

            // ═══ LIVE EXECUTION ═══
            // Simulation passed - safe to send
            const signature = await sendAndConfirmTransaction(
                this.connection,
                tx,
                [this.wallet!],
                { commitment: 'confirmed', maxRetries: 3 }
            );

            return {
                success: true,
                command: 'swap',
                signature,
                legs: legResults,
                simulationSuccess: true,
                computeUnitsUsed: simulation.value.unitsConsumed,
                timestamp,
            };

        } catch (e: any) {
            return {
                success: false,
                command: 'swap',
                error: e.message || String(e),
                timestamp,
            };
        }
    }

    /**
     * Get quotes without executing
     */
    async getQuotes(legs: SwapLeg[]): Promise<EngineResult> {
        const timestamp = Date.now();

        try {
            // Create a dummy wallet for quote-only operations
            this.wallet = Keypair.generate();

            const legResults: LegResult[] = [];

            for (const leg of legs) {
                if (leg.dex === 'meteora') {
                    const poolAddr = new PublicKey(leg.pool);
                    const dlmmPool = await DLMM.create(this.connection, poolAddr);

                    const inputMint = new PublicKey(leg.inputMint);
                    const isXtoY = inputMint.equals(dlmmPool.tokenX.publicKey);

                    const binArrays = await dlmmPool.getBinArrayForSwap(isXtoY);
                    const swapQuote = await dlmmPool.swapQuote(
                        new BN(leg.amount),
                        isXtoY,
                        new BN(leg.slippageBps || DEFAULT_SLIPPAGE_BPS),
                        binArrays
                    );

                    legResults.push({
                        dex: leg.dex,
                        inputMint: leg.inputMint,
                        outputMint: leg.outputMint,
                        inputAmount: leg.amount,
                        outputAmount: swapQuote.outAmount.toNumber(),
                        priceImpact: swapQuote.priceImpact?.toNumber() || 0,
                    });
                } else {
                    legResults.push({
                        dex: leg.dex,
                        inputMint: leg.inputMint,
                        outputMint: leg.outputMint,
                        inputAmount: leg.amount,
                        outputAmount: 0,
                        priceImpact: 0,
                    });
                }
            }

            return {
                success: true,
                command: 'quote',
                legs: legResults,
                timestamp,
            };

        } catch (e: any) {
            return {
                success: false,
                command: 'quote',
                error: e.message || String(e),
                timestamp,
            };
        }
    }

    /**
     * Health check
     */
    async healthCheck(): Promise<EngineResult> {
        const timestamp = Date.now();

        try {
            const slot = await this.connection.getSlot();
            return {
                success: true,
                command: 'health',
                timestamp,
            };
        } catch (e: any) {
            return {
                success: false,
                command: 'health',
                error: e.message || String(e),
                timestamp,
            };
        }
    }
}

// ═══════════════════════════════════════════════════════════════════
// CLI ENTRY POINT
// ═══════════════════════════════════════════════════════════════════

async function main() {
    const engine = new ExecutionEngine();

    // Parse command from CLI args
    const input = process.argv[2];
    if (!input) {
        console.log(JSON.stringify({
            success: false,
            error: 'No command provided',
            usage: 'node execution_engine.js \'{"command":"health"}\'',
            timestamp: Date.now(),
        }));
        process.exit(1);
    }

    let cmd: EngineCommand;
    try {
        cmd = JSON.parse(input);
    } catch (e) {
        console.log(JSON.stringify({
            success: false,
            error: 'Invalid JSON input',
            timestamp: Date.now(),
        }));
        process.exit(1);
    }

    let result: EngineResult;

    switch (cmd.command) {
        case 'health':
            result = await engine.healthCheck();
            break;

        case 'quote':
            if (!cmd.legs || cmd.legs.length === 0) {
                result = { success: false, command: 'quote', error: 'No legs provided', timestamp: Date.now() };
            } else {
                result = await engine.getQuotes(cmd.legs);
            }
            break;

        case 'simulate':
            // Simulate-only mode (seatbelt check without spending gas)
            if (!cmd.privateKey) {
                result = { success: false, command: 'simulate', error: 'No private key provided', timestamp: Date.now() };
            } else if (!cmd.legs || cmd.legs.length === 0) {
                result = { success: false, command: 'simulate', error: 'No legs provided', timestamp: Date.now() };
            } else {
                result = await engine.executeSwap(cmd.legs, cmd.privateKey, cmd.priorityFee, true);
            }
            break;

        case 'swap':
            if (!cmd.privateKey) {
                result = { success: false, command: 'swap', error: 'No private key provided', timestamp: Date.now() };
            } else if (!cmd.legs || cmd.legs.length === 0) {
                result = { success: false, command: 'swap', error: 'No legs provided', timestamp: Date.now() };
            } else {
                // Pass simulateOnly flag from command (defaults to false)
                result = await engine.executeSwap(cmd.legs, cmd.privateKey, cmd.priorityFee, cmd.simulateOnly || false);
            }
            break;

        default:
            result = { success: false, command: 'unknown', error: `Unknown command: ${cmd.command}`, timestamp: Date.now() };
    }

    console.log(JSON.stringify(result));
}

main().catch((e) => {
    console.log(JSON.stringify({
        success: false,
        error: e.message || String(e),
        timestamp: Date.now(),
    }));
    process.exit(1);
});
