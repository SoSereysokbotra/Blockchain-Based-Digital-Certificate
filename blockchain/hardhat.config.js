import hardhatToolboxMochaEthers from "@nomicfoundation/hardhat-toolbox-mocha-ethers";
import "dotenv/config";

// Public Amoy RPC as a fallback so `compile` and `test` work with no .env at
// all; set AMOY_RPC_URL to your own Alchemy/Infura endpoint before deploying.
const AMOY_RPC_URL = process.env.AMOY_RPC_URL || "https://rpc-amoy.polygon.technology";
const DEPLOYER_PRIVATE_KEY = process.env.DEPLOYER_PRIVATE_KEY ?? "";

/** @type import('hardhat/config').HardhatUserConfig */
export default {
  plugins: [hardhatToolboxMochaEthers],

  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },

  networks: {
    // In-memory chain used by `npx hardhat test`. No gas cost, no testnet.
    hardhat: {
      type: "edr-simulated",
      chainType: "l1",
    },
    // Local blockchain node
    localhost: {
      type: "http",
      chainType: "l1",
      url: "http://127.0.0.1:8545",
      chainId: 31337,
    },
    // Polygon Amoy testnet (SRS 7.2). Only used by the deploy script.
    amoy: {
      type: "http",
      chainType: "l1",
      url: AMOY_RPC_URL,
      chainId: 80002,
      accounts: DEPLOYER_PRIVATE_KEY ? [DEPLOYER_PRIVATE_KEY] : [],
    },
    // Ethereum Sepolia testnet
    sepolia: {
      type: "http",
      chainType: "l1",
      url: process.env.SEPOLIA_RPC_URL || "https://ethereum-sepolia-rpc.publicnode.com",
      chainId: 11155111,
      accounts: DEPLOYER_PRIVATE_KEY ? [DEPLOYER_PRIVATE_KEY] : [],
    },
    // Ethereum Holesky testnet
    holesky: {
      type: "http",
      chainType: "l1",
      url: process.env.HOLESKY_RPC_URL || "https://ethereum-holesky-rpc.publicnode.com",
      chainId: 17000,
      accounts: DEPLOYER_PRIVATE_KEY ? [DEPLOYER_PRIVATE_KEY] : [],
    },
  },

  paths: {
    sources: "./contracts",
    tests: { mocha: "./test" },
  },
};
