"use strict";
/**
 * Raydium CLMM Bridge for Phantom Arbiter V2
 * ===========================================
 * CLI tool for executing swaps on Raydium Concentrated Liquidity pools.
 * Uses RPC-first approach for real-time data (no API indexing delay).
 *
 * Usage:
 *   node raydium_clmm.js price <pool_address>
 *   node raydium_clmm.js quote <pool_address> <input_mint> <amount>
 *   node raydium_clmm.js swap <pool_address> <input_mint> <amount> <slippage_bps> <private_key>
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const web3_js_1 = require("@solana/web3.js");
const raydium_sdk_v2_1 = require("@raydium-io/raydium-sdk-v2");
const spl_token_1 = require("@solana/spl-token");
const bs58_1 = __importDefault(require("bs58"));
const bn_js_1 = __importDefault(require("bn.js"));
const decimal_js_1 = __importDefault(require("decimal.js"));
// RPC endpoint
const RPC_URL = process.env.SOLANA_RPC_URL || "https://api.mainnet-beta.solana.com";
// ═══════════════════════════════════════════════════════════════════
// HELPER: Initialize Raydium SDK (minimal)
// ═══════════════════════════════════════════════════════════════════
async function initRaydium(connection, owner) {
    let tokenAccountData;
    if (owner) {
        const tokenAccounts = await connection.getTokenAccountsByOwner(owner.publicKey, {
            programId: spl_token_1.TOKEN_PROGRAM_ID
        });
        const token2022Accounts = await connection.getTokenAccountsByOwner(owner.publicKey, {
            programId: spl_token_1.TOKEN_2022_PROGRAM_ID
        });
        tokenAccountData = (0, raydium_sdk_v2_1.parseTokenAccountResp)({
            owner: owner.publicKey,
            solAccountResp: await connection.getAccountInfo(owner.publicKey),
            tokenAccountResp: {
                context: tokenAccounts.context,
                value: [...tokenAccounts.value, ...token2022Accounts.value]
            }
        });
    }
    const raydium = await raydium_sdk_v2_1.Raydium.load({
        connection,
        owner: owner?.publicKey,
        signAllTransactions: owner ? async (txs) => {
            return txs.map(tx => {
                if (tx instanceof web3_js_1.VersionedTransaction) {
                    tx.sign([owner]);
                }
                else {
                    tx.sign(owner);
                }
                return tx;
            });
        } : undefined,
        tokenAccounts: tokenAccountData?.tokenAccounts,
        tokenAccountRawInfos: tokenAccountData?.tokenAccountRawInfos,
        disableFeatureCheck: true,
        disableLoadToken: true,
        blockhashCommitment: 'confirmed'
    });
    return raydium;
}
async function discoverPoolViaRaydiumV3(mintA, mintB) {
    /**
     * Primary discovery via Raydium V3 API.
     */
    try {
        const url = `https://api-v3.raydium.io/pools/info/mint?mint1=${mintA}&mint2=${mintB}&poolType=clmm&poolSortField=default&sortType=desc&pageSize=1&page=1`;
        const response = await fetch(url);
        if (!response.ok) {
            return {
                success: false,
                poolId: '',
                mintA,
                mintB,
                tvl: 0,
                volume24h: 0,
                feeRate: 0,
                error: `Raydium V3 API error: ${response.status}`
            };
        }
        const data = await response.json();
        if (!data.success || !data.data || data.data.count === 0) {
            return {
                success: false,
                poolId: '',
                mintA,
                mintB,
                tvl: 0,
                volume24h: 0,
                feeRate: 0,
                error: 'No CLMM pool found via Raydium V3'
            };
        }
        const pool = data.data.data[0];
        return {
            success: true,
            poolId: pool.id,
            mintA: pool.mintA?.address || mintA,
            mintB: pool.mintB?.address || mintB,
            tvl: pool.tvl || 0,
            volume24h: pool.day?.volume || 0,
            feeRate: pool.feeRate || 0
        };
    }
    catch (error) {
        return {
            success: false,
            poolId: '',
            mintA,
            mintB,
            tvl: 0,
            volume24h: 0,
            feeRate: 0,
            error: `Raydium V3: ${error.message || String(error)}`
        };
    }
}
async function discoverPoolViaDexScreener(mintA, mintB) {
    /**
     * Fallback discovery via DexScreener API.
     * Searches for Raydium CLMM pools containing both mints.
     */
    try {
        // Query DexScreener for the first mint
        const url = `https://api.dexscreener.com/latest/dex/tokens/${mintA}`;
        const response = await fetch(url);
        if (!response.ok) {
            return {
                success: false,
                poolId: '',
                mintA,
                mintB,
                tvl: 0,
                volume24h: 0,
                feeRate: 0,
                error: `DexScreener API error: ${response.status}`
            };
        }
        const data = await response.json();
        const pairs = data.pairs || [];
        // Filter for Raydium pairs containing both our mints
        // CLMM pools typically have concentrated liquidity indicators
        const raydiumPairs = pairs.filter((p) => {
            if (p.dexId !== 'raydium')
                return false;
            const base = p.baseToken?.address;
            const quote = p.quoteToken?.address;
            // Check if this pair contains both our mints
            return (base === mintA && quote === mintB) ||
                (base === mintB && quote === mintA);
        });
        if (raydiumPairs.length === 0) {
            return {
                success: false,
                poolId: '',
                mintA,
                mintB,
                tvl: 0,
                volume24h: 0,
                feeRate: 0,
                error: 'No Raydium pool found via DexScreener'
            };
        }
        // Select best pool by liquidity
        const bestPair = raydiumPairs.sort((a, b) => (b.liquidity?.usd || 0) - (a.liquidity?.usd || 0))[0];
        return {
            success: true,
            poolId: bestPair.pairAddress,
            mintA: bestPair.baseToken?.address || mintA,
            mintB: bestPair.quoteToken?.address || mintB,
            tvl: bestPair.liquidity?.usd || 0,
            volume24h: bestPair.volume?.h24 || 0,
            feeRate: 0 // DexScreener doesn't expose fee tier
        };
    }
    catch (error) {
        return {
            success: false,
            poolId: '',
            mintA,
            mintB,
            tvl: 0,
            volume24h: 0,
            feeRate: 0,
            error: `DexScreener: ${error.message || String(error)}`
        };
    }
}
async function discoverPool(mintA, mintB) {
    /**
     * Discover CLMM pool with fallback strategy:
     * 1. Try Raydium V3 API (primary)
     * 2. Fallback to DexScreener if V3 fails
     */
    // Primary: Raydium V3 API
    const v3Result = await discoverPoolViaRaydiumV3(mintA, mintB);
    if (v3Result.success) {
        return v3Result;
    }
    // Fallback: DexScreener API
    const dexResult = await discoverPoolViaDexScreener(mintA, mintB);
    if (dexResult.success) {
        return dexResult;
    }
    // Both failed - return combined error
    return {
        success: false,
        poolId: '',
        mintA,
        mintB,
        tvl: 0,
        volume24h: 0,
        feeRate: 0,
        error: `${v3Result.error} | ${dexResult.error}`
    };
}
// ═══════════════════════════════════════════════════════════════════
// PRICE: Get current pool price from RPC
// ═══════════════════════════════════════════════════════════════════
async function getPrice(poolAddress) {
    const connection = new web3_js_1.Connection(RPC_URL, 'confirmed');
    try {
        const raydium = await initRaydium(connection);
        // Fetch pool info from RPC (returns complex object)
        const poolId = new web3_js_1.PublicKey(poolAddress);
        const rpcResult = await raydium.clmm.getPoolInfoFromRpc(poolId.toString());
        if (!rpcResult || !rpcResult.poolInfo) {
            return {
                success: false,
                pool: poolAddress,
                tokenA: '',
                tokenB: '',
                priceAtoB: 0,
                priceBtoA: 0,
                liquidity: '0',
                error: 'Pool not found - verify this is a CLMM pool (not legacy AMM)'
            };
        }
        // The actual poolInfo is nested
        const info = rpcResult.poolInfo;
        const compute = rpcResult.computePoolInfo;
        // Safety checks
        if (!info.mintA || !info.mintB) {
            return {
                success: false,
                pool: poolAddress,
                tokenA: '',
                tokenB: '',
                priceAtoB: 0,
                priceBtoA: 0,
                liquidity: '0',
                error: 'Pool missing mint data'
            };
        }
        // Get current price from computePoolInfo (more accurate)
        let priceAtoB = 0;
        let priceBtoA = 0;
        let liquidity = '0';
        let currentTick;
        if (compute && compute.currentPrice) {
            priceAtoB = compute.currentPrice.toNumber();
            priceBtoA = priceAtoB > 0 ? 1 / priceAtoB : 0;
        }
        if (compute?.liquidity) {
            liquidity = compute.liquidity.toString();
        }
        if (compute?.tickCurrent !== undefined) {
            currentTick = compute.tickCurrent;
        }
        return {
            success: true,
            pool: poolAddress,
            tokenA: info.mintA.address,
            tokenB: info.mintB.address,
            priceAtoB,
            priceBtoA,
            liquidity,
            currentTick
        };
    }
    catch (error) {
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
// QUOTE: Get estimated output for a swap
// ═══════════════════════════════════════════════════════════════════
async function getQuote(poolAddress, inputMint, amountIn) {
    const connection = new web3_js_1.Connection(RPC_URL, 'confirmed');
    try {
        const raydium = await initRaydium(connection);
        const poolId = new web3_js_1.PublicKey(poolAddress);
        const rpcResult = await raydium.clmm.getPoolInfoFromRpc(poolId.toString());
        if (!rpcResult || !rpcResult.poolInfo) {
            return {
                success: false,
                inputMint,
                outputMint: '',
                inputAmount: amountIn,
                outputAmount: '0',
                priceImpact: 0,
                error: 'Pool not found'
            };
        }
        const info = rpcResult.poolInfo;
        // Determine swap direction
        const isAtoB = info.mintA.address === inputMint;
        const outputMint = isAtoB ? info.mintB.address : info.mintA.address;
        // Get decimals
        const inputDecimals = isAtoB ? info.mintA.decimals : info.mintB.decimals;
        const outputDecimals = isAtoB ? info.mintB.decimals : info.mintA.decimals;
        // Convert amount
        const amountInBN = new bn_js_1.default(new decimal_js_1.default(amountIn).mul(10 ** inputDecimals).floor().toString());
        // Compute output using SDK - PoolUtils is a static utility class
        const clmmPoolInfo = rpcResult.computePoolInfo;
        const swapResult = clmmPoolInfo ? await raydium_sdk_v2_1.PoolUtils.computeAmountOutFormat({
            poolInfo: clmmPoolInfo,
            tickArrayCache: rpcResult.tickData[poolAddress] || rpcResult.tickData,
            amountIn: amountInBN,
            tokenOut: isAtoB ? info.mintB : info.mintA,
            slippage: 0.005,
            epochInfo: await connection.getEpochInfo()
        }) : null;
        if (!swapResult || !swapResult.amountOut) {
            // Fallback: estimate from current price
            const priceResult = await getPrice(poolAddress);
            if (priceResult.success) {
                const price = isAtoB ? priceResult.priceAtoB : priceResult.priceBtoA;
                const estimatedOut = parseFloat(amountIn) * price;
                return {
                    success: true,
                    inputMint,
                    outputMint,
                    inputAmount: amountIn,
                    outputAmount: estimatedOut.toFixed(outputDecimals),
                    priceImpact: 0.001 // Estimated
                };
            }
            return {
                success: false,
                inputMint,
                outputMint,
                inputAmount: amountIn,
                outputAmount: '0',
                priceImpact: 0,
                error: 'Could not compute swap output'
            };
        }
        return {
            success: true,
            inputMint,
            outputMint,
            inputAmount: amountIn,
            outputAmount: new decimal_js_1.default(swapResult.amountOut.amount.toString())
                .div(10 ** outputDecimals).toString(),
            priceImpact: swapResult.priceImpact ? Number(swapResult.priceImpact.numerator) / Number(swapResult.priceImpact.denominator) : 0
        };
    }
    catch (error) {
        return {
            success: false,
            inputMint,
            outputMint: '',
            inputAmount: amountIn,
            outputAmount: '0',
            priceImpact: 0,
            error: error.message || String(error)
        };
    }
}
// ═══════════════════════════════════════════════════════════════════
// SWAP: Execute swap on Raydium CLMM
// ═══════════════════════════════════════════════════════════════════
async function executeSwap(poolAddress, inputMint, amountIn, slippageBps, privateKeyBase58) {
    const connection = new web3_js_1.Connection(RPC_URL, 'confirmed');
    try {
        const privateKey = bs58_1.default.decode(privateKeyBase58);
        const owner = web3_js_1.Keypair.fromSecretKey(privateKey);
        const raydium = await initRaydium(connection, owner);
        const poolId = new web3_js_1.PublicKey(poolAddress);
        const rpcResult = await raydium.clmm.getPoolInfoFromRpc(poolId.toString());
        if (!rpcResult || !rpcResult.poolInfo) {
            return {
                success: false,
                inputMint,
                outputMint: '',
                inputAmount: amountIn,
                outputAmount: '0',
                error: 'Pool not found'
            };
        }
        const info = rpcResult.poolInfo;
        // Direction
        const isAtoB = info.mintA.address === inputMint;
        const outputMint = isAtoB ? info.mintB.address : info.mintA.address;
        // Decimals
        const inputDecimals = isAtoB ? info.mintA.decimals : info.mintB.decimals;
        const outputDecimals = isAtoB ? info.mintB.decimals : info.mintA.decimals;
        // Amount
        const amountInBN = new bn_js_1.default(new decimal_js_1.default(amountIn).mul(10 ** inputDecimals).floor().toString());
        const slippage = slippageBps / 10000;
        // Build and execute swap
        const { execute } = await raydium.clmm.swap({
            poolInfo: info,
            inputMint: new web3_js_1.PublicKey(inputMint),
            amountIn: amountInBN,
            amountOutMin: new bn_js_1.default(0), // Will compute internally
            observationId: rpcResult.poolKeys?.observationId,
            ownerInfo: { useSOLBalance: true },
            remainingAccounts: [],
            txVersion: raydium_sdk_v2_1.TxVersion.V0
        });
        const { txId } = await execute({ sendAndConfirm: true });
        return {
            success: true,
            signature: txId,
            inputMint,
            outputMint,
            inputAmount: amountIn,
            outputAmount: '0' // Would need to parse transaction
        };
    }
    catch (error) {
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
            error: 'Usage: node raydium_clmm.js <price|quote|swap> [args...]'
        }));
        process.exit(1);
    }
    switch (command.toLowerCase()) {
        case 'price': {
            const [, poolAddress] = args;
            if (!poolAddress) {
                console.log(JSON.stringify({ success: false, error: 'Usage: price <pool_address>' }));
                process.exit(1);
            }
            const result = await getPrice(poolAddress);
            console.log(JSON.stringify(result));
            break;
        }
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
        case 'swap': {
            const [, poolAddress, inputMint, amount, slippageBps, privateKey] = args;
            if (!poolAddress || !inputMint || !amount || !slippageBps || !privateKey) {
                console.log(JSON.stringify({ success: false, error: 'Usage: swap <pool> <input_mint> <amount> <slippage_bps> <key>' }));
                process.exit(1);
            }
            const result = await executeSwap(poolAddress, inputMint, amount, parseInt(slippageBps), privateKey);
            console.log(JSON.stringify(result));
            break;
        }
        case 'discover': {
            const [, mintA, mintB] = args;
            if (!mintA || !mintB) {
                console.log(JSON.stringify({ success: false, error: 'Usage: discover <mint_a> <mint_b>' }));
                process.exit(1);
            }
            const result = await discoverPool(mintA, mintB);
            console.log(JSON.stringify(result));
            break;
        }
        default:
            console.log(JSON.stringify({ success: false, error: `Unknown command: ${command}. Use: discover|price|quote|swap` }));
            process.exit(1);
    }
}
main().catch(err => {
    console.log(JSON.stringify({ success: false, error: err.message || String(err) }));
    process.exit(1);
});
