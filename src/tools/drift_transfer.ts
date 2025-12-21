import { Connection, Keypair, PublicKey } from '@solana/web3.js';
import { Wallet } from '@coral-xyz/anchor';
import { DriftClient, User, initialize, QUOTE_SPOT_MARKET_INDEX, BN } from '@drift-labs/sdk';
import * as fs from 'fs';
import * as path from 'path';
import * as dotenv from 'dotenv';

// Load environment
dotenv.config({ path: path.join(__dirname, '../../.env') });

const RPC_URL = process.env.RPC_URL || 'https://api.mainnet-beta.solana.com';
const WALLET_PATH = process.env.WALLET_PATH || path.join(process.env.USERPROFILE || '', '.config/solana/id.json');

// USDC decimals on Solana
const USDC_DECIMALS = 6;

async function loadWallet(): Promise<Keypair> {
    const secretKey = JSON.parse(fs.readFileSync(WALLET_PATH, 'utf-8'));
    return Keypair.fromSecretKey(Uint8Array.from(secretKey));
}

async function getDriftClient(): Promise<{ client: DriftClient; user: User }> {
    const connection = new Connection(RPC_URL, 'confirmed');
    const keypair = await loadWallet();
    const wallet = new Wallet(keypair);

    // Initialize Drift SDK
    const sdkConfig = initialize({ env: 'mainnet-beta' });

    const client = new DriftClient({
        connection,
        wallet,
        programID: new PublicKey(sdkConfig.DRIFT_PROGRAM_ID),
        env: 'mainnet-beta',
    });

    await client.subscribe();

    const user = client.getUser();

    return { client, user };
}

async function getBalance(): Promise<{ usdc: number; freeCollateral: number }> {
    const { client, user } = await getDriftClient();

    try {
 * Usage:
 * npx ts - node src / tools / drift_transfer.ts deposit 10     # Deposit $10 USDC
            * npx ts - node src / tools / drift_transfer.ts withdraw 10    # Withdraw $10 USDC
                * npx ts - node src / tools / drift_transfer.ts balance        # Check balance
                    * 
 * Or via Python wrapper:
 * python main.py drift deposit 10
            * python main.py drift withdraw 10
                * python main.py drift balance
                    */

        import { Connection, Keypair, PublicKey } from '@solana/web3.js';
        import { Wallet } from '@coral-xyz/anchor';
        import { DriftClient, User, initialize, QUOTE_SPOT_MARKET_INDEX, BN } from '@drift-labs/sdk';
        import * as fs from 'fs';
        import * as path from 'path';
        import * as dotenv from 'dotenv';

        // Load environment
        dotenv.config({ path: path.join(__dirname, '../../.env') });

        const RPC_URL = process.env.RPC_URL || 'https://api.mainnet-beta.solana.com';
        const WALLET_PATH = process.env.WALLET_PATH || path.join(process.env.USERPROFILE || '', '.config/solana/id.json');

        // USDC decimals on Solana
        const USDC_DECIMALS = 6;

        async function loadWallet(): Promise<Keypair> {
            const secretKey = JSON.parse(fs.readFileSync(WALLET_PATH, 'utf-8'));
            return Keypair.fromSecretKey(Uint8Array.from(secretKey));
        }

        async function getDriftClient(): Promise<{ client: DriftClient; user: User }> {
            const connection = new Connection(RPC_URL, 'confirmed');
            const keypair = await loadWallet();
            const wallet = new Wallet(keypair);

            // Initialize Drift SDK
            const sdkConfig = initialize({ env: 'mainnet-beta' });

            const client = new DriftClient({
                connection,
                wallet,
                programID: new PublicKey(sdkConfig.DRIFT_PROGRAM_ID),
                env: 'mainnet-beta',
            });

            await client.subscribe();

            const user = client.getUser();

            return { client, user };
        }

        async function getBalance(): Promise<{ usdc: number; freeCollateral: number }> {
            const { client, user } = await getDriftClient();

            try {
                // Get USDC spot position (market index 0)
                const spotPosition = user.getSpotPosition(QUOTE_SPOT_MARKET_INDEX);
                const usdcBalance = spotPosition
                    ? Number(spotPosition.scaledBalance) / (10 ** USDC_DECIMALS)
                    : 0;

                // Get free collateral
                const freeCollateral = Number(user.getFreeCollateral()) / (10 ** USDC_DECIMALS);

                console.log(`\n📊 Drift Balance:`);
                console.log(`   USDC: $${usdcBalance.toFixed(2)}`);
                console.log(`   Free Collateral: $${freeCollateral.toFixed(2)}`);

                return { usdc: usdcBalance, freeCollateral };
            } finally {
                await client.unsubscribe();
            }
        }

        async function deposit(amountUsd: number): Promise<void> {
            const { client } = await getDriftClient();

            try {
                const amountBN = new BN(amountUsd * (10 ** USDC_DECIMALS));

                console.log(`\n💰 Depositing $${amountUsd} USDC to Drift...`);

                const txSig = await client.deposit(
                    amountBN,
                    QUOTE_SPOT_MARKET_INDEX,  // USDC
                );

                console.log(`✅ Deposit successful!`);
                console.log(`   TX: https://solscan.io/tx/${txSig}`);

            } finally {
                await client.unsubscribe();
            }
        }

        async function withdraw(amountUsd: number): Promise<void> {
            const { client } = await getDriftClient();

            try {
                const amountBN = new BN(amountUsd * (10 ** USDC_DECIMALS));

                console.log(`\n💸 Withdrawing $${amountUsd} USDC from Drift...`);

                const txSig = await client.withdraw(
                    amountBN,
                    QUOTE_SPOT_MARKET_INDEX,  // USDC
                    undefined,  // Associated token account (auto-detect)
                    false,      // reduceOnly
                );

                console.log(`✅ Withdrawal successful!`);
                console.log(`   TX: https://solscan.io/tx/${txSig}`);

            } finally {
                await client.unsubscribe();
            }
        }

        // CLI Entry Point
        async function main() {
            const args = process.argv.slice(2);
            const command = args[0];
            const amount = parseFloat(args[1] || '0');

            if (!command) {
                console.log(`
Drift Transfer CLI
==================
Usage:
  drift_transfer.ts balance           Check Drift balance
  drift_transfer.ts deposit <amount>  Deposit USDC to Drift
  drift_transfer.ts withdraw <amount> Withdraw USDC from Drift

Examples:
  npx ts-node drift_transfer.ts deposit 10
  npx ts-node drift_transfer.ts withdraw 5
  npx ts-node drift_transfer.ts balance
        `);
                return;
            }

            try {
                switch (command.toLowerCase()) {
                    case 'balance':
                        await getBalance();
                        break;
                    case 'deposit':
                        if (amount <= 0) {
                            console.error('❌ Please specify a valid amount');
                            return;
                        }
                        await deposit(amount);
                        break;
                    case 'withdraw':
                        if (amount <= 0) {
                            console.error('❌ Please specify a valid amount');
                            return;
                        }
                        await withdraw(amount);
                        break;
                    default:
                        console.error(`❌ Unknown command: ${command}`);
                }
            } catch (error) {
                console.error(`❌ Error: ${error}`);
                process.exit(1);
            }
        }

        main();
