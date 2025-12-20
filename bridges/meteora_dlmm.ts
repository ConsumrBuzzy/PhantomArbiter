/**
 * Meteora DLMM Bridge for Phantom Arbiter
 * ========================================
 * CLI tool for executing swaps and fetching quotes from Meteora DLMM pools.
 * 
 * Usage:
 *   node meteora_bridge.js quote <pool_address> <input_mint> <amount>
 *   node meteora_bridge.js swap <pool_address> <input_mint> <amount> <slippage_bps> <private_key>
 * 
 * Output: JSON string to stdout
 * 
 * Build: npm run build
 */

import { Connection, PublicKey, Keypair, VersionedTransaction } from '@solana/web3.js';
import DLMM from '@meteora-ag/dlmm';
import bs58 from 'bs58';
import BN from 'bn.js';

// RPC endpoint - can be overridden via env
const RPC_URL = process.env.SOLANA_RPC_URL || "https://api.mainnet-beta.solana.com";

interface QuoteResult {
    success: boolean;
    inputMint: string;
    outputMint: string;
    inputAmount: string;
    outputAmount: string;
    priceImpact: number;
    fee: string;
    error?: string;
}

interface SwapResult {
    success: boolean;
    signature?: string;
    inputMint: string;
    outputMint: string;
    inputAmount: string;
    outputAmount: string;
    error?: string;
}

interface PriceResult {
    success: boolean;
    pool: string;
    tokenX: string;
    tokenY: string;
    priceXtoY: number;
    priceYtoX: number;
    activeBinId: number;
    error?: string;
}

// ═══════════════════════════════════════════════════════════════════
// QUOTE: Get expected output for a swap (no execution)
// ═══════════════════════════════════════════════════════════════════
async function getQuote(
    poolAddress: string,
    inputMint: string,
    amountIn: string
): Promise<QuoteResult> {
    try {
        const connection = new Connection(RPC_URL, 'confirmed');
        const poolPubKey = new PublicKey(poolAddress);
        const inputMintPubKey = new PublicKey(inputMint);

        // Load DLMM pool
        const dlmmPool = await DLMM.create(connection, poolPubKey);

        // Determine swap direction (X to Y or Y to X)
        const tokenX = dlmmPool.tokenX.publicKey;
        const tokenY = dlmmPool.tokenY.publicKey;
        const swapYtoX = inputMintPubKey.equals(tokenY);

        const outputMint = swapYtoX ? tokenX : tokenY;

        // Get quote
        const amountInBN = new BN(amountIn);
        const binArrays = await dlmmPool.getBinArrayForSwap(swapYtoX);
        const quote = dlmmPool.swapQuote(amountInBN, swapYtoX, new BN(0), binArrays);

        return {
            success: true,
            inputMint: inputMint,
            outputMint: outputMint.toBase58(),
            inputAmount: amountIn,
            outputAmount: quote.outAmount.toString(),
            priceImpact: quote.priceImpact.toNumber(),
            fee: quote.fee.toString()
        };

    } catch (err: any) {
        return {
            success: false,
            inputMint: inputMint,
            outputMint: "",
            inputAmount: amountIn,
            outputAmount: "0",
            priceImpact: 0,
            fee: "0",
            error: err.message || String(err)
        };
    }
}

// ═══════════════════════════════════════════════════════════════════
// PRICE: Get current pool price (for scanning)
// ═══════════════════════════════════════════════════════════════════
async function getPrice(poolAddress: string): Promise<PriceResult> {
    try {
        const connection = new Connection(RPC_URL, 'confirmed');
        const poolPubKey = new PublicKey(poolAddress);

        // Load DLMM pool
        const dlmmPool = await DLMM.create(connection, poolPubKey);

        // Get active bin price
        const activeBin = await dlmmPool.getActiveBin();
        const pricePerToken = dlmmPool.fromPricePerLamport(
            Number(activeBin.price)
        );

        return {
            success: true,
            pool: poolAddress,
            tokenX: dlmmPool.tokenX.publicKey.toBase58(),
            tokenY: dlmmPool.tokenY.publicKey.toBase58(),
            priceXtoY: pricePerToken,
            priceYtoX: 1 / pricePerToken,
            activeBinId: activeBin.binId
        };

    } catch (err: any) {
        return {
            success: false,
            pool: poolAddress,
            tokenX: "",
            tokenY: "",
            priceXtoY: 0,
            priceYtoX: 0,
            activeBinId: 0,
            error: err.message || String(err)
        };
    }
}

// ═══════════════════════════════════════════════════════════════════
// SWAP: Execute a swap on Meteora DLMM
// ═══════════════════════════════════════════════════════════════════
async function executeSwap(
    poolAddress: string,
    inputMint: string,
    amountIn: string,
    slippageBps: number,
    privateKeyBase58: string
): Promise<SwapResult> {
    try {
        const connection = new Connection(RPC_URL, 'confirmed');
        const poolPubKey = new PublicKey(poolAddress);
        const inputMintPubKey = new PublicKey(inputMint);

        // Load wallet
        const secretKey = bs58.decode(privateKeyBase58);
        const wallet = Keypair.fromSecretKey(secretKey);

        // Load DLMM pool
        const dlmmPool = await DLMM.create(connection, poolPubKey);

        // Determine swap direction
        const tokenX = dlmmPool.tokenX.publicKey;
        const tokenY = dlmmPool.tokenY.publicKey;
        const swapYtoX = inputMintPubKey.equals(tokenY);
        const outputMint = swapYtoX ? tokenX : tokenY;

        // Get quote first
        const amountInBN = new BN(amountIn);
        const binArrays = await dlmmPool.getBinArrayForSwap(swapYtoX);
        const quote = dlmmPool.swapQuote(amountInBN, swapYtoX, new BN(slippageBps), binArrays);

        // Build swap transaction
        const swapTx = await dlmmPool.swap({
            inToken: inputMintPubKey,
            binArraysPubkey: quote.binArraysPubkey,
            inAmount: amountInBN,
            lbPair: poolPubKey,
            user: wallet.publicKey,
            minOutAmount: quote.minOutAmount,
            outToken: outputMint
        });

        // Sign and send
        const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash();

        // Handle both legacy and versioned transactions
        let signature: string;

        if (swapTx instanceof VersionedTransaction) {
            swapTx.message.recentBlockhash = blockhash;
            swapTx.sign([wallet]);
            signature = await connection.sendTransaction(swapTx);
        } else {
            swapTx.recentBlockhash = blockhash;
            swapTx.feePayer = wallet.publicKey;
            swapTx.sign(wallet);
            signature = await connection.sendRawTransaction(swapTx.serialize());
        }

        // Wait for confirmation
        await connection.confirmTransaction({
            signature,
            blockhash,
            lastValidBlockHeight
        }, 'confirmed');

        return {
            success: true,
            signature,
            inputMint,
            outputMint: outputMint.toBase58(),
            inputAmount: amountIn,
            outputAmount: quote.outAmount.toString()
        };

    } catch (err: any) {
        return {
            success: false,
            inputMint,
            outputMint: "",
            inputAmount: amountIn,
            outputAmount: "0",
            error: err.message || String(err)
        };
    }
}

// ═══════════════════════════════════════════════════════════════════
// CLI ENTRY POINT
// ═══════════════════════════════════════════════════════════════════
async function main() {
    const args = process.argv.slice(2);
    const command = args[0];

    if (!command) {
        console.log(JSON.stringify({
            success: false,
            error: "Usage: node meteora_bridge.js <quote|price|swap> [args...]"
        }));
        process.exit(1);
    }

    let result: any;

    switch (command.toLowerCase()) {
        case 'quote':
            // quote <pool_address> <input_mint> <amount>
            if (args.length < 4) {
                result = { success: false, error: "quote requires: pool_address input_mint amount" };
            } else {
                result = await getQuote(args[1], args[2], args[3]);
            }
            break;

        case 'price':
            // price <pool_address>
            if (args.length < 2) {
                result = { success: false, error: "price requires: pool_address" };
            } else {
                result = await getPrice(args[1]);
            }
            break;

        case 'swap':
            // swap <pool_address> <input_mint> <amount> <slippage_bps> <private_key>
            if (args.length < 6) {
                result = { success: false, error: "swap requires: pool_address input_mint amount slippage_bps private_key" };
            } else {
                result = await executeSwap(args[1], args[2], args[3], parseInt(args[4]), args[5]);
            }
            break;

        default:
            result = { success: false, error: `Unknown command: ${command}` };
    }

    // Output ONLY JSON for Python to parse
    console.log(JSON.stringify(result));
}

main().catch(err => {
    console.log(JSON.stringify({ success: false, error: err.message || String(err) }));
    process.exit(1);
});
