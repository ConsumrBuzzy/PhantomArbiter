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
    SystemProgram,
    sendAndConfirmTransaction,
    LAMPORTS_PER_SOL,
} from '@solana/web3.js';
import DLMM from '@meteora-ag/dlmm';
import {
    WhirlpoolContext,
    buildWhirlpoolClient,
    ORCA_WHIRLPOOL_PROGRAM_ID,
    PDAUtil,
    SwapUtils,
    swapQuoteByInputToken,
    WhirlpoolIx,
} from '@orca-so/whirlpools-sdk';
import { AnchorProvider, Wallet } from '@coral-xyz/anchor';
import { Percentage } from '@orca-so/common-sdk';
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
    jitoTipLamports?: number;  // Tip amount for Jito bundles (default: 10000)
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
const DEFAULT_JITO_TIP = 10_000;         // 10k lamports (~$0.002)

// ═══ HELIUS SENDER (Free 15 TPS) ═══
// Bypasses standard RPC limits, auto-routes to fastest validator
const HELIUS_API_KEY = process.env.HELIUS_API_KEY || '';
const HELIUS_SENDER_URL = HELIUS_API_KEY
    ? `https://mainnet.helius-rpc.com/?api-key=${HELIUS_API_KEY}`
    : '';

// Verified Jito Tip Accounts (2025)
const JITO_TIP_ACCOUNTS = [
    '96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5',
    'HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRE',
    'Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY',
    'ADaUMid9yfUytqMBgTQ37Kq7PevX2dKS2nxMxSQrcFpM',
    'DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh',
    'ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt',
    'DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL',
    '3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT',
];

// Jito Block Engine URL
const JITO_BLOCK_ENGINE_URL = 'https://mainnet.block-engine.jito.wtf/api/v1/bundles';

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
     * Build Jito tip instruction
     * Tips a random Jito validator to include our bundle privately
     */
    private buildJitoTipIx(lamports: number) {
        // Pick a random tip account to spread the load
        const randomTipAccount = new PublicKey(
            JITO_TIP_ACCOUNTS[Math.floor(Math.random() * JITO_TIP_ACCOUNTS.length)]
        );

        return SystemProgram.transfer({
            fromPubkey: this.wallet!.publicKey,
            toPubkey: randomTipAccount,
            lamports: lamports,
        });
    }

    /**
     * Send transaction bundle via Jito Block Engine
     * Ensures all-or-nothing execution and sandwich protection
     */
    private async sendJitoBundle(txs: VersionedTransaction[]): Promise<string> {
        const serializedTxs = txs.map(tx => bs58.encode(tx.serialize()));

        const response = await fetch(JITO_BLOCK_ENGINE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                id: 1,
                method: 'sendBundle',
                params: [serializedTxs]
            })
        });

        const result = await response.json();

        if (result.error) {
            throw new Error(`Jito bundle failed: ${JSON.stringify(result.error)}`);
        }

        return result.result; // This is the bundle ID
    }

    /**
     * Send transaction via Helius Sender endpoint
     * Free 15 TPS, auto-routes to fastest validator
     */
    private async sendViaHelius(tx: Transaction | VersionedTransaction): Promise<string> {
        if (!HELIUS_SENDER_URL) {
            throw new Error('HELIUS_API_KEY not configured');
        }

        const serialized = tx.serialize();
        const base64 = serialized.toString('base64');

        const response = await fetch(HELIUS_SENDER_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                id: 1,
                method: 'sendTransaction',
                params: [
                    base64,
                    {
                        encoding: 'base64',
                        skipPreflight: false,
                        preflightCommitment: 'confirmed',
                        maxRetries: 3,
                    }
                ]
            })
        });

        const result = await response.json();

        if (result.error) {
            throw new Error(`Helius send failed: ${JSON.stringify(result.error)}`);
        }

        return result.result;
    }

    /**
     * Wait for transaction confirmation
     */
    private async confirmTransaction(signature: string, timeout: number = 30000): Promise<boolean> {
        const startTime = Date.now();

        while (Date.now() - startTime < timeout) {
            try {
                const status = await this.connection.getSignatureStatus(signature);
                if (status.value?.confirmationStatus === 'confirmed' ||
                    status.value?.confirmationStatus === 'finalized') {
                    return true;
                }
                if (status.value?.err) {
                    return false;
                }
            } catch (e) {
                // Ignore and retry
            }
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        return false;
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
     * Build Orca Whirlpool swap instruction
     * Uses concentrated liquidity pools for efficient swaps
     */
    private async buildOrcaSwap(leg: SwapLeg): Promise<any> {
        const poolAddr = new PublicKey(leg.pool);
        const inputMint = new PublicKey(leg.inputMint);

        // Create Anchor provider for Orca SDK
        const anchorWallet = new Wallet(this.wallet!);
        const provider = new AnchorProvider(
            this.connection,
            anchorWallet,
            { commitment: 'confirmed' }
        );

        // Initialize Orca client
        const ctx = WhirlpoolContext.from(
            this.connection,
            anchorWallet,
            ORCA_WHIRLPOOL_PROGRAM_ID
        );
        const client = buildWhirlpoolClient(ctx);

        // Fetch pool data
        const whirlpool = await client.getPool(poolAddr);
        const whirlpoolData = whirlpool.getData();

        // Determine swap direction (A to B or B to A)
        const aToB = inputMint.equals(whirlpoolData.tokenMintA);

        // Get swap quote
        const slippage = Percentage.fromFraction(
            leg.slippageBps || DEFAULT_SLIPPAGE_BPS,
            10000
        );

        const quote = await swapQuoteByInputToken(
            whirlpool,
            inputMint,
            new BN(leg.amount),
            slippage,
            ORCA_WHIRLPOOL_PROGRAM_ID,
            await client.getFetcher(),
            { maxAge: 0 } // Force refresh of account data
        );

        // Build swap instruction
        const swapTx = await whirlpool.swap(quote);

        return {
            instructions: swapTx.compressIx ? [swapTx.compressIx] : [],
            quote: {
                inputAmount: leg.amount,
                outputAmount: quote.estimatedAmountOut.toNumber(),
                minOutputAmount: quote.otherAmountThreshold.toNumber(),
                priceImpact: 0, // Orca doesn't provide this directly
            }
        };
    }

    /**
     * Execute atomic multi-leg swap
     * @param simulateOnly If true, simulate but don't send (seatbelt mode)
     * @param jitoTipLamports Tip amount for Jito bundles (0 = no tip)
     */
    async executeSwap(
        legs: SwapLeg[],
        privateKey: string,
        priorityFee?: number,
        simulateOnly: boolean = false,
        jitoTipLamports: number = 0
    ): Promise<EngineResult> {
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

            // ═══ JITO TIP (must be LAST instruction) ═══
            if (jitoTipLamports > 0) {
                const tipIx = this.buildJitoTipIx(jitoTipLamports);
                tx.add(tipIx);
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
            let signature: string;

            // 1. Convert to VersionedTransaction for Jito/Modern Sending
            const messageV0 = new TransactionMessage({
                payerKey: this.wallet!.publicKey,
                recentBlockhash: blockhash,
                instructions: tx.instructions,
            }).compileToV0Message();
            const versionedTx = new VersionedTransaction(messageV0);
            versionedTx.sign([this.wallet!]);

            if (jitoTipLamports > 0) {
                // Use Jito Bundle for guaranteed atomicity and speed
                // Note: We currently send as a single-transaction bundle for simplicity
                signature = await this.sendJitoBundle([versionedTx]);

                // Bundle ID is used for confirmation tracking
                const confirmed = await this.confirmTransaction(signature);
                if (!confirmed) {
                    return {
                        success: false,
                        command: 'swap',
                        signature,
                        legs: legResults,
                        error: 'Jito Bundle not confirmed - likely expired or landed after height',
                        timestamp,
                    };
                }
            } else if (HELIUS_SENDER_URL) {
                // Use Helius for faster, rate-limit-free sending
                signature = await this.sendViaHelius(versionedTx);
                // Wait for confirmation
                const confirmed = await this.confirmTransaction(signature);
                if (!confirmed) {
                    return {
                        success: false,
                        command: 'swap',
                        signature,
                        legs: legResults,
                        error: 'Transaction not confirmed within timeout',
                        timestamp,
                    };
                }
            } else {
                // Fallback to standard RPC
                signature = await this.connection.sendTransaction(versionedTx, {
                    skipPreflight: true,
                    maxRetries: 2
                });
                const confirmed = await this.confirmTransaction(signature);
                if (!confirmed) {
                    return {
                        success: false,
                        command: 'swap',
                        signature,
                        error: 'Standard RPC send failed to confirm',
                        timestamp,
                    };
                }
            }

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

    // V94 DAEMON MODE
    const args = process.argv.slice(2);
    if (args[0] === 'daemon') {
        const readline = require('readline');
        const rl = readline.createInterface({
            input: process.stdin,
            output: process.stdout,
            terminal: false
        });

        console.error("DEBUG: Execution Engine Daemon Ready");

        rl.on('line', async (line: string) => {
            if (!line.trim()) return;
            const timestamp = Date.now();
            try {
                const cmd: EngineCommand = JSON.parse(line);
                let result: EngineResult;

                switch (cmd.command) {
                    case 'health':
                        result = await engine.healthCheck();
                        break;

                    case 'quote':
                        if (!cmd.legs || cmd.legs.length === 0) {
                            result = { success: false, command: 'quote', error: 'No legs provided', timestamp };
                        } else {
                            result = await engine.getQuotes(cmd.legs);
                        }
                        break;

                    case 'simulate':
                        if (!cmd.privateKey) {
                            result = { success: false, command: 'simulate', error: 'No private key provided', timestamp };
                        } else if (!cmd.legs || cmd.legs.length === 0) {
                            result = { success: false, command: 'simulate', error: 'No legs provided', timestamp };
                        } else {
                            result = await engine.executeSwap(
                                cmd.legs,
                                cmd.privateKey,
                                cmd.priorityFee,
                                true, // simulateOnly
                                cmd.jitoTipLamports || 0
                            );
                        }
                        break;

                    case 'swap':
                        if (!cmd.privateKey) {
                            result = { success: false, command: 'swap', error: 'No private key provided', timestamp };
                        } else if (!cmd.legs || cmd.legs.length === 0) {
                            result = { success: false, command: 'swap', error: 'No legs provided', timestamp };
                        } else {
                            result = await engine.executeSwap(
                                cmd.legs,
                                cmd.privateKey,
                                cmd.priorityFee,
                                cmd.simulateOnly || false,
                                cmd.jitoTipLamports || 0
                            );
                        }
                        break;

                    default:
                        result = { success: false, command: 'unknown', error: `Unknown command: ${cmd.command}`, timestamp };
                }
                console.log(JSON.stringify(result));
            } catch (e: any) {
                console.log(JSON.stringify({
                    success: false,
                    command: 'error',
                    error: e.message || String(e),
                    timestamp
                }));
            }
        });
        return;
    }

    // LEGACY MODE (One-off)
    const input = args[0];
    if (!input) {
        console.log(JSON.stringify({
            success: false,
            error: 'No command provided',
            usage: 'node execution_engine.js \'{"command":"health"}\' OR node execution_engine.js daemon',
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
            if (!cmd.privateKey) {
                result = { success: false, command: 'simulate', error: 'No private key provided', timestamp: Date.now() };
            } else if (!cmd.legs || cmd.legs.length === 0) {
                result = { success: false, command: 'simulate', error: 'No legs provided', timestamp: Date.now() };
            } else {
                result = await engine.executeSwap(
                    cmd.legs, cmd.privateKey, cmd.priorityFee, true, cmd.jitoTipLamports || 0
                );
            }
            break;

        case 'swap':
            if (!cmd.privateKey) {
                result = { success: false, command: 'swap', error: 'No private key provided', timestamp: Date.now() };
            } else if (!cmd.legs || cmd.legs.length === 0) {
                result = { success: false, command: 'swap', error: 'No legs provided', timestamp: Date.now() };
            } else {
                result = await engine.executeSwap(
                    cmd.legs,
                    cmd.privateKey,
                    cmd.priorityFee,
                    cmd.simulateOnly || false,
                    cmd.jitoTipLamports || 0
                );
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
