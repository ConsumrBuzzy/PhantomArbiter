/**
 * Raydium CLMM Bridge for Phantom Arbiter
 * ========================================
 * CLI tool for executing swaps and fetching quotes from Raydium Concentrated Liquidity pools.
 * 
 * Usage:
 *   node raydium_clmm.js quote <pool_address> <input_mint> <amount>
 *   node raydium_clmm.js swap <pool_address> <input_mint> <amount> <slippage_bps> <private_key_base58>
 *   node raydium_clmm.js price <pool_address>
 */

import {
    Connection,
    PublicKey,
    Keypair,
    Transaction,
    VersionedTransaction,
    sendAndConfirmTransaction
} from '@solana/web3.js';
import { Raydium, TxVersion, parseTokenAccountResp } from '@raydium-io/raydium-sdk-v2';
import { TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID } from '@solana/spl-token';
import bs58 from 'bs58';
import BN from 'bn.js';
import Decimal from 'decimal.js';

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
    tokenA: string;
    tokenB: string;
    priceAtoB: number;
    priceBtoA: number;
    liquidity: string;
    error?: string;
}

// ═══════════════════════════════════════════════════════════════════
// HELPER: Initialize Raydium SDK
// ═══════════════════════════════════════════════════════════════════
async function initRaydium(connection: Connection, owner?: Keypair): Promise<Raydium> {
    // Fetch token accounts if we have an owner
    let tokenAccountData: ReturnType<typeof parseTokenAccountResp> | undefined;

    if (owner) {
        const tokenAccounts = await connection.getTokenAccountsByOwner(owner.publicKey, {
            programId: TOKEN_PROGRAM_ID
        });
        const token2022Accounts = await connection.getTokenAccountsByOwner(owner.publicKey, {
            programId: TOKEN_2022_PROGRAM_ID
        });

        tokenAccountData = parseTokenAccountResp({
            owner: owner.publicKey,
            solAccountResp: await connection.getAccountInfo(owner.publicKey),
            tokenAccountResp: {
                context: tokenAccounts.context,
                value: [...tokenAccounts.value, ...token2022Accounts.value]
            }
        });
    }

    const raydium = await Raydium.load({
        connection,
        owner: owner?.publicKey,
        signAllTransactions: owner ? async (txs) => {
            return txs.map(tx => {
                if (tx instanceof VersionedTransaction) {
                    tx.sign([owner]);
                } else {
                    tx.sign(owner);
                }
                return tx;
            });
        } : undefined,
        tokenAccounts: tokenAccountData?.tokenAccounts,
        tokenAccountRawInfos: tokenAccountData?.tokenAccountRawInfos,
        disableFeatureCheck: true,
        disableLoadToken: false,
        blockhashCommitment: 'confirmed'
    });

    return raydium;
}

// ═══════════════════════════════════════════════════════════════════
// QUOTE: Get estimated output for a swap
// ═══════════════════════════════════════════════════════════════════
async function getQuote(
    poolAddress: string,
    inputMint: string,
    amountIn: string
): Promise<QuoteResult> {
    const connection = new Connection(RPC_URL, 'confirmed');

    try {
        const raydium = await initRaydium(connection);

        // Load the CLMM pool
        const poolId = new PublicKey(poolAddress);
        const poolInfo = await raydium.clmm.getPoolInfoFromRpc(poolId.toString());

        if (!poolInfo) {
            return {
                success: false,
                inputMint,
                outputMint: '',
                inputAmount: amountIn,
                outputAmount: '0',
                priceImpact: 0,
                fee: '0',
                error: 'Pool not found'
            };
        }

        // Determine direction
        const inputMintPubkey = new PublicKey(inputMint);
        const isBaseToQuote = poolInfo.mintA.address === inputMint;
        const outputMint = isBaseToQuote ? poolInfo.mintB.address : poolInfo.mintA.address;

        // Get input decimals
        const inputDecimals = isBaseToQuote ? poolInfo.mintA.decimals : poolInfo.mintB.decimals;
        const amountInBN = new BN(new Decimal(amountIn).mul(10 ** inputDecimals).floor().toString());

        // Compute swap
        const { minAmountOut, remainingAccounts, executionPrice, priceImpact, fee } =
            await raydium.clmm.computeAmountOut({
                poolInfo,
                amountIn: amountInBN,
                tokenOut: new PublicKey(outputMint),
                slippage: 0.01 // 1% for quote purposes
            });

        const outputDecimals = isBaseToQuote ? poolInfo.mintB.decimals : poolInfo.mintA.decimals;

        return {
            success: true,
            inputMint,
            outputMint,
            inputAmount: amountIn,
            outputAmount: new Decimal(minAmountOut.toString()).div(10 ** outputDecimals).toString(),
            priceImpact: priceImpact?.toNumber() || 0,
            fee: fee?.toString() || '0'
        };

    } catch (error: any) {
        return {
            success: false,
            inputMint,
            outputMint: '',
            inputAmount: amountIn,
            outputAmount: '0',
            priceImpact: 0,
            fee: '0',
            error: error.message || String(error)
        };
    }
}

// ═══════════════════════════════════════════════════════════════════
// PRICE: Get current pool price (for scanning)
// ═══════════════════════════════════════════════════════════════════
async function getPrice(poolAddress: string): Promise<PriceResult> {
    const connection = new Connection(RPC_URL, 'confirmed');

    try {
        const raydium = await initRaydium(connection);

        const poolId = new PublicKey(poolAddress);
        const poolInfo = await raydium.clmm.getPoolInfoFromRpc(poolId.toString());

        if (!poolInfo) {
            return {
                success: false,
                pool: poolAddress,
                tokenA: '',
                tokenB: '',
                priceAtoB: 0,
                priceBtoA: 0,
                liquidity: '0',
                error: 'Pool not found'
            };
        }

        // Current price from sqrtPriceX64
        const sqrtPrice = new Decimal(poolInfo.sqrtPriceX64.toString());
        const priceAtoB = sqrtPrice.div(new Decimal(2).pow(64)).pow(2).toNumber();
        const priceBtoA = priceAtoB > 0 ? 1 / priceAtoB : 0;

        return {
            success: true,
            pool: poolAddress,
            tokenA: poolInfo.mintA.address,
            tokenB: poolInfo.mintB.address,
            priceAtoB,
            priceBtoA,
            liquidity: poolInfo.liquidity?.toString() || '0'
        };

    } catch (error: any) {
        return {
            success: false,
            pool: poolAddress,
            tokenA: '',
            tokenB: '',
            priceAtoB: 0,
            priceBtoA: 0,
            liquidity: '0',
            error: error.message || String(error)
        };
    }
}

// ═══════════════════════════════════════════════════════════════════
// SWAP: Execute a swap on Raydium CLMM
// ═══════════════════════════════════════════════════════════════════
async function executeSwap(
    poolAddress: string,
    inputMint: string,
    amountIn: string,
    slippageBps: number,
    privateKeyBase58: string
): Promise<SwapResult> {
    const connection = new Connection(RPC_URL, 'confirmed');

    try {
        // Load keypair
        const privateKey = bs58.decode(privateKeyBase58);
        const owner = Keypair.fromSecretKey(privateKey);

        const raydium = await initRaydium(connection, owner);

        // Load pool
        const poolId = new PublicKey(poolAddress);
        const poolInfo = await raydium.clmm.getPoolInfoFromRpc(poolId.toString());

        if (!poolInfo) {
            return {
                success: false,
                inputMint,
                outputMint: '',
                inputAmount: amountIn,
                outputAmount: '0',
                error: 'Pool not found'
            };
        }

        // Direction
        const isBaseToQuote = poolInfo.mintA.address === inputMint;
        const outputMint = isBaseToQuote ? poolInfo.mintB.address : poolInfo.mintA.address;

        // Amounts
        const inputDecimals = isBaseToQuote ? poolInfo.mintA.decimals : poolInfo.mintB.decimals;
        const outputDecimals = isBaseToQuote ? poolInfo.mintB.decimals : poolInfo.mintA.decimals;
        const amountInBN = new BN(new Decimal(amountIn).mul(10 ** inputDecimals).floor().toString());

        // Compute swap with slippage
        const slippage = slippageBps / 10000;
        const { minAmountOut, remainingAccounts } = await raydium.clmm.computeAmountOut({
            poolInfo,
            amountIn: amountInBN,
            tokenOut: new PublicKey(outputMint),
            slippage
        });

        // Build transaction
        const { execute, transaction } = await raydium.clmm.swap({
            poolInfo,
            inputMint: new PublicKey(inputMint),
            amountIn: amountInBN,
            amountOutMin: minAmountOut,
            observationId: poolInfo.observationId,
            ownerInfo: {
                useSOLBalance: true
            },
            remainingAccounts,
            txVersion: TxVersion.V0
        });

        // Execute
        const { txId } = await execute({ sendAndConfirm: true });

        return {
            success: true,
            signature: txId,
            inputMint,
            outputMint,
            inputAmount: amountIn,
            outputAmount: new Decimal(minAmountOut.toString()).div(10 ** outputDecimals).toString()
        };

    } catch (error: any) {
        return {
            success: false,
            inputMint,
            outputMint: '',
            inputAmount: amountIn,
            outputAmount: '0',
            error: error.message || String(error)
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
            error: 'Usage: node raydium_clmm.js <quote|swap|price> [args...]'
        }));
        process.exit(1);
    }

    switch (command.toLowerCase()) {
        case 'quote': {
            const [, poolAddress, inputMint, amount] = args;
            if (!poolAddress || !inputMint || !amount) {
                console.log(JSON.stringify({ success: false, error: 'Usage: quote <pool> <input_mint> <amount>' }));
                process.exit(1);
            }
            const result = await getQuote(poolAddress, inputMint, amount);
            console.log(JSON.stringify(result));
            break;
        }

        case 'price': {
            const [, poolAddress] = args;
            if (!poolAddress) {
                console.log(JSON.stringify({ success: false, error: 'Usage: price <pool>' }));
                process.exit(1);
            }
            const result = await getPrice(poolAddress);
            console.log(JSON.stringify(result));
            break;
        }

        case 'swap': {
            const [, poolAddress, inputMint, amount, slippageBps, privateKey] = args;
            if (!poolAddress || !inputMint || !amount || !slippageBps || !privateKey) {
                console.log(JSON.stringify({ success: false, error: 'Usage: swap <pool> <input_mint> <amount> <slippage_bps> <private_key>' }));
                process.exit(1);
            }
            const result = await executeSwap(poolAddress, inputMint, amount, parseInt(slippageBps), privateKey);
            console.log(JSON.stringify(result));
            break;
        }

        default:
            console.log(JSON.stringify({ success: false, error: `Unknown command: ${command}` }));
            process.exit(1);
    }
}

main().catch(err => {
    console.log(JSON.stringify({ success: false, error: err.message || String(err) }));
    process.exit(1);
});
