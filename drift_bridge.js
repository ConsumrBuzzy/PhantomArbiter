const { DriftClient, Wallet, BN, PositionDirection, OrderType, MarketType } = require('@drift-labs/sdk');
const { Connection, Keypair, PublicKey } = require('@solana/web3.js');
const bs58 = require('bs58');

async function main() {
    try {
        const pkStr = process.env.SOLANA_PRIVATE_KEY;
        if (!pkStr) throw new Error("SOLANA_PRIVATE_KEY not found in ENV");

        // Decode Keypair
        let secretKey;
        if (pkStr.includes("[")) {
            secretKey = Uint8Array.from(JSON.parse(pkStr));
        } else {
            secretKey = bs58.decode(pkStr);
        }
        const keypair = Keypair.fromSecretKey(secretKey);
        const wallet = new Wallet(keypair);

        const rpcUrl = process.env.SOLANA_RPC_URL || "https://api.mainnet-beta.solana.com";
        const connection = new Connection(rpcUrl, "confirmed");

        // Initialize Drift Client
        const driftClient = new DriftClient({
            connection,
            wallet,
            env: 'mainnet-beta',
            accountSubscription: { type: 'websocket' }
        });

        // Add logging to stderr (so stdout remains JSON only)
        console.error(`[Bridge] Initializing DriftClient on ${rpcUrl}...`);

        await driftClient.subscribe();
        console.error(`[Bridge] Subscribed. User Public Key: ${driftClient.getUser().userAccountPublicKey.toString()}`);

        const instructions = [];

        // 1. Check User Existence (using getUserAccount() which returns null/undefined if not found? 
        // Actually, we check if the account exists on-chain via connection
        // SDK user.exists() checks cache. Since we just subscribed, cache should be fresh?
        // BUT if account is new, cache might be empty.
        // Best check: fetch raw account info.

        const userKey = driftClient.getUser().userAccountPublicKey;
        const accountInfo = await connection.getAccountInfo(userKey);

        if (accountInfo === null) {
            console.error(`[Bridge] User Account ${userKey.toString()} NOT FOUND. Creating InitializeUser instruction...`);
            const initIx = await driftClient.getInitializeUserInstruction();
            instructions.push(initIx);
        } else {
            console.error(`[Bridge] User Account ${userKey.toString()} EXISTS. Skipping initialization.`);
        }

        // 2. Build PlacePerpOrder
        // Args: node script.js <market_index> <amount_atomic> <is_short>
        const marketIndex = parseInt(process.argv[2] || "0"); // 0 = SOL-PERP
        const amountAtomic = process.argv[3] || "0";
        const isShort = (process.argv[4] === "true"); // "true" or "false"

        console.error(`[Bridge] Building Order: Market=${marketIndex}, Amount=${amountAtomic}, Short=${isShort}`);

        const orderParams = {
            orderType: OrderType.MARKET,
            marketType: MarketType.PERP,
            direction: isShort ? PositionDirection.SHORT : PositionDirection.LONG,
            baseAssetAmount: new BN(amountAtomic),
            price: new BN(0), // Market Order
            marketIndex: marketIndex,
            reduceOnly: false,
            postOnly: false,
            immediateOrCancel: true,
            // Defaults for others
        };

        const orderIx = await driftClient.getPlacePerpOrderInstruction(orderParams);
        instructions.push(orderIx);

        // 3. Serialize for Python
        const serialized = instructions.map(ix => ({
            programId: ix.programId.toString(),
            keys: ix.keys.map(k => ({
                pubkey: k.pubkey.toString(),
                isSigner: k.isSigner,
                isWritable: k.isWritable
            })),
            data: ix.data.toString('base64')
        }));

        // Output JSON to stdout
        console.log(JSON.stringify(serialized));

        await driftClient.unsubscribe();

    } catch (e) {
        console.error(`[Bridge] Error: ${e.message}`);
        console.error(e.stack);
        process.exit(1);
    }
}

main();
