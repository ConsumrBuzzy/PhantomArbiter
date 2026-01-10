const { Connection, PublicKey, LAMPORTS_PER_SOL } = require('@solana/web3.js');
const { getAssociatedTokenAddress, TOKEN_PROGRAM_ID } = require('@solana/spl-token');

async function preflight() {
    const conn = new Connection('https://api.mainnet-beta.solana.com');
    const DRIFT = new PublicKey('dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH');
    const USDC_MINT = new PublicKey('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v');
    const WALLET = new PublicKey('99G8vXM4YjULWtmzshsVCJ7AJeb8Psr8dfWuHbwGxry3');

    console.log('=== PHASE 2 PRE-FLIGHT CHECKLIST ===\n');
    console.log('Wallet:', WALLET.toBase58());

    // 1. Check SOL Balance
    const solBalance = await conn.getBalance(WALLET);
    const solAmount = solBalance / LAMPORTS_PER_SOL;
    console.log(`\n[1] SOL Balance: ${solAmount.toFixed(4)} SOL`);
    console.log(`    Status: ${solAmount >= 0.05 ? '✅ OK (>0.05 SOL for fees)' : '⚠️ LOW - need ~0.05 SOL for fees'}`);

    // 2. Check USDC Balance (wallet)
    try {
        const usdcAta = await getAssociatedTokenAddress(USDC_MINT, WALLET);
        const usdcInfo = await conn.getTokenAccountBalance(usdcAta);
        const usdcAmount = parseFloat(usdcInfo.value.uiAmount);
        console.log(`\n[2] USDC Balance (Wallet): $${usdcAmount.toFixed(2)}`);
        console.log(`    Status: ${usdcAmount >= 2.0 ? '✅ OK (>$2 for trade)' : '⚠️ Need $2+ USDC for Jupiter swap'}`);
    } catch (e) {
        console.log('\n[2] USDC Balance (Wallet): $0.00');
        console.log('    Status: ⚠️ No USDC ATA found');
    }

    // 3. Check Drift User Account
    const [userPDA] = PublicKey.findProgramAddressSync(
        [Buffer.from('user'), WALLET.toBuffer(), Buffer.from([0, 0])],
        DRIFT
    );
    console.log(`\n[3] Drift User Account: ${userPDA.toBase58()}`);
    const userInfo = await conn.getAccountInfo(userPDA);
    console.log(`    Status: ${userInfo ? '✅ Initialized' : '❌ NOT INITIALIZED - run initializeUser first'}`);

    // 4. Summary
    console.log('\n=== SUMMARY ===');
    if (solAmount >= 0.05 && userInfo) {
        console.log('✅ Ready for Phase 2 execution');
        console.log('   Ensure USDC is deposited in Drift account before live run');
    } else {
        console.log('⚠️ Pre-flight checks incomplete - see warnings above');
    }
}

preflight().catch(console.error);
