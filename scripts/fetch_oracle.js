const { Connection, PublicKey } = require('@solana/web3.js');

async function main() {
    const conn = new Connection('https://api.mainnet-beta.solana.com');
    const DRIFT = new PublicKey('dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH');

    // SOL-PERP Market (index 0)
    const [perpMarketPDA] = PublicKey.findProgramAddressSync(
        [Buffer.from('perp_market'), Buffer.from([0, 0])],
        DRIFT
    );

    // USDC Spot Market (index 0 - quote asset)
    const [spotMarketPDA] = PublicKey.findProgramAddressSync(
        [Buffer.from('spot_market'), Buffer.from([0, 0])],
        DRIFT
    );

    console.log('=== PERP MARKET (SOL-PERP index 0) ===');
    console.log('PDA:', perpMarketPDA.toBase58());

    const perpInfo = await conn.getAccountInfo(perpMarketPDA);
    if (perpInfo) {
        // Oracle is at offset 48 in PerpMarket
        const oracleBytes = perpInfo.data.slice(48, 80);
        console.log('Oracle:', new PublicKey(oracleBytes).toBase58());
    }

    console.log('\n=== SPOT MARKET (USDC index 0) ===');
    console.log('PDA:', spotMarketPDA.toBase58());

    const spotInfo = await conn.getAccountInfo(spotMarketPDA);
    if (spotInfo) {
        // Oracle is at offset 48 in SpotMarket
        const oracleBytes = spotInfo.data.slice(48, 80);
        console.log('Oracle:', new PublicKey(oracleBytes).toBase58());
    }

    // Also derive Drift State
    const [statePDA] = PublicKey.findProgramAddressSync(
        [Buffer.from('drift_state')],
        DRIFT
    );
    console.log('\n=== DRIFT STATE ===');
    console.log('State PDA:', statePDA.toBase58());
}

main().catch(console.error);
