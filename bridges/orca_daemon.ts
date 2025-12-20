/**
 * Orca Whirlpool Bridge for Phantom Arbiter V2
 * ===========================================
 * CLI tool for executing swaps on Orca Whirlpools.
 * Uses persistent Daemon mode for sub-50ms latency.
 */

import { Connection, PublicKey, Keypair, VersionedTransaction } from "@solana/web3.js";
import {
    WhirlpoolContext,
    buildWhirlpoolClient,
    ORCA_WHIRLPOOL_PROGRAM_ID,
    PDAUtil,
    PriceMath,
    swapQuoteByInputToken,
    IGeneralTokenAccountInfo
} from "@orca-so/whirlpools-sdk";
import { DecimalUtil, Percentage } from "@orca-so/common-sdk";
import { Decimal } from "decimal.js";
import bs58 from "bs58";

const RPC_URL = process.env.SOLANA_RPC_URL || "https://api.mainnet-beta.solana.com";

interface PriceResult {
    success: boolean;
    pool: string;
    tokenA: string; // Token A is always the one with smaller address in Whirlpool
    tokenB: string;
    price: number;
    sqrtPrice: string;
    tickCurrentIndex: number;
    liquidity: string;
    error?: string;
}

interface QuoteResult {
    success: boolean;
    inputMint: string;
    outputMint: string;
    inputAmount: string;
    outputAmount: string;
    priceImpact: number;
    error?: string;
}

// ═══════════════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════════════
async function initOrca(connection: Connection, owner?: Keypair) {
    const wallet = owner ? {
        publicKey: owner.publicKey,
        signTransaction: async (tx: any) => { tx.sign([owner]); return tx; },
        signAllTransactions: async (txs: any[]) => { txs.forEach(t => t.sign([owner])); return txs; }
    } : {
        publicKey: new PublicKey("11111111111111111111111111111111"),
        signTransaction: async (tx: any) => tx,
        signAllTransactions: async (txs: any[]) => txs
    };

    const ctx = WhirlpoolContext.from(
        connection,
        wallet as any,
        ORCA_WHIRLPOOL_PROGRAM_ID
    );

    return buildWhirlpoolClient(ctx);
}

// ═══════════════════════════════════════════════════════════════════
// PRICE
// ═══════════════════════════════════════════════════════════════════
async function getPrice(poolAddress: string, client?: any, connection?: Connection): Promise<PriceResult> {
    try {
        if (!client) {
            const conn = connection || new Connection(RPC_URL, 'confirmed');
            client = await initOrca(conn);
        }

        const poolKey = new PublicKey(poolAddress);
        const whirlpool = await client.getPool(poolKey);

        // Refresh data (lightweight fetch)
        await whirlpool.refreshData();
        const data = whirlpool.getData();

        const tokenA = data.tokenMintA.toBase58();
        const tokenB = data.tokenMintB.toBase58();
        const price = PriceMath.sqrtPriceX64ToPrice(data.sqrtPrice, 9, 6); // Decimals hardcoded for now, need fetch

        return {
            success: true,
            pool: poolAddress,
            tokenA,
            tokenB,
            price: parseFloat(price.toFixed(6)),
            sqrtPrice: data.sqrtPrice.toString(),
            tickCurrentIndex: data.tickCurrentIndex,
            liquidity: data.liquidity.toString()
        };

    } catch (error: any) {
        return {
            success: false,
            pool: poolAddress,
            tokenA: '', tokenB: '',
            price: 0, sqrtPrice: '0', tickCurrentIndex: 0, liquidity: '0',
            error: error.message || String(error)
        };
    }
}

// ═══════════════════════════════════════════════════════════════════
// DAEMON MAIN
// ═══════════════════════════════════════════════════════════════════
async function main() {
    const args = process.argv.slice(2);
    if (args[0] !== 'daemon') {
        console.log("Usage: node orca_daemon.js daemon");
        return;
    }

    const connection = new Connection(RPC_URL, 'confirmed');
    const client = await initOrca(connection);

    console.error("DEBUG: Orca Daemon Ready");

    const readline = require('readline');
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
        terminal: false
    });

    rl.on('line', async (line: string) => {
        if (!line.trim()) return;
        try {
            const req = JSON.parse(line);
            let result = {};

            if (req.cmd === 'price') {
                result = await getPrice(req.pool, client, connection);
            }

            console.log(JSON.stringify(result));
        } catch (e: any) {
            console.log(JSON.stringify({ success: false, error: e.message }));
        }
    });
}

main();
