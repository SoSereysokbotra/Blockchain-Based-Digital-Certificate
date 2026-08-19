const { ethers } = require('ethers');
const mnemonic = "outer account misery flash birth motor lottery wheel hobby that snap hour";
const HDNode = ethers.HDNodeWallet || ethers.Wallet;
for (let i = 0; i < 5; i++) {
  try {
    const path = `m/44'/60'/${i}'/0/0`;
    let wallet;
    if (ethers.HDNodeWallet) {
        // ethers v6
        wallet = ethers.HDNodeWallet.fromPhrase(mnemonic, undefined, path);
    } else {
        wallet = ethers.Wallet.fromMnemonic(mnemonic, path);
    }
    console.log(`Account ${i}: ${wallet.address} - ${wallet.privateKey}`);
  } catch (e) {
    console.error(e);
  }
}
