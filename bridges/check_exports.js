const sdk = require('@raydium-io/raydium-sdk-v2');
console.log("Liquidity exported?", !!sdk.Liquidity);
console.log("LiquidityStateV4 exported?", !!sdk.LiquidityStateV4);
console.log("Keys:", Object.keys(sdk).slice(0, 10));
