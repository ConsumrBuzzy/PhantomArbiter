const { DriftClient } = require('@drift-labs/sdk');
const { PublicKey } = require('@solana/web3.js');
const fs = require('fs');

async function inspect() {
    const idlPath = 'node_modules/@drift-labs/sdk/src/idl/drift.json';
    const idl = JSON.parse(fs.readFileSync(idlPath, 'utf8'));

    const placePerpOrder = idl.instructions.find(ix => ix.name === 'placePerpOrder');
    console.log('--- PlacePerpOrder IDL Accounts ---');
    console.log(JSON.stringify(placePerpOrder.accounts, null, 2));
}

inspect();
