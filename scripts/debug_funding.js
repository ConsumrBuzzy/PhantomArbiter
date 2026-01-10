const { Connection, PublicKey, Keypair } = require('@solana/web3.js');
const { AnchorProvider, Program, Wallet } = require('@coral-xyz/anchor');
const idl = require('../node_modules/@drift-labs/sdk/src/idl/drift.json');

const DRIFT_PROGRAM_ID = new PublicKey("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH");

async function main() {
    const conn = new Connection('https://api.mainnet-beta.solana.com');
    const wallet = new Wallet(new Keypair());
    const provider = new AnchorProvider(conn, wallet, {});
    const program = new Program(idl, DRIFT_PROGRAM_ID, provider);

    const [perpMarketPDA] = PublicKey.findProgramAddressSync(
        [Buffer.from('perp_market'), Buffer.from([0, 0])],
        DRIFT_PROGRAM_ID
    );

    console.log("Fetching account:", perpMarketPDA.toString());
    const account = await program.account.perpMarket.fetch(perpMarketPDA);

    const name = String.fromCharCode(...account.name).replace(/\0/g, '');
    console.log("Market Name:", name);

    console.log("AMM Last Funding Rate (RAW):", account.amm.lastFundingRate.toString());
    console.log("AMM Last Funding Rate (Human):", account.amm.lastFundingRate.toNumber() / 1e9);

    // Check if last24hAvgFundingRate exists in the object structure
    if (account.amm.last24hAvgFundingRate) {
        console.log("24h Avg Funding (Human):", account.amm.last24hAvgFundingRate.toNumber() / 1e9);
    } else {
        console.log("last24hAvgFundingRate field not found in IDL response object");
    }
}

main().catch(console.error);
