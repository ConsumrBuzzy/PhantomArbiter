const { Connection, PublicKey } = require('@solana/web3.js');

async function main() {
    const conn = new Connection('https://api.mainnet-beta.solana.com');
    const DRIFT = new PublicKey('dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH');

    // Derive SOL-PERP market PDA (index 0)
    const [perpMarketPDA] = PublicKey.findProgramAddressSync(
        [Buffer.from('perp_market'), Buffer.from([0, 0])],
        DRIFT
    );

    console.log('SOL-PERP Market PDA:', perpMarketPDA.toBase58());

    const info = await conn.getAccountInfo(perpMarketPDA);
    if (!info) {
        console.log('Account not found');
        return;
    }

    console.log('Account size:', info.data.length, 'bytes');

    // Check potential oracle positions in PerpMarket struct
    // Based on Drift IDL, oracle is typically after discriminator and pubkey fields
    const offsets = [8, 40, 48, 80, 112, 144, 176, 208];

    console.log('\nScanning for potential oracle pubkeys:');
    for (const offset of offsets) {
        try {
            const bytes = info.data.slice(offset, offset + 32);
            const pk = new PublicKey(bytes);
            // Filter out likely non-pubkey values (all zeros, etc)
            if (pk.toBase58() !== '11111111111111111111111111111111') {
                console.log(`  Offset ${offset}: ${pk.toBase58()}`);
            }
        } catch (e) { }
    }

    // The oracle in PerpMarket struct is at offset 48 per Drift IDL
    console.log('\n=== CANONICAL ORACLE (offset 48) ===');
    const oracleBytes = info.data.slice(48, 80);
    console.log('Oracle:', new PublicKey(oracleBytes).toBase58());
}

main().catch(console.error);
