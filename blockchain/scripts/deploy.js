/**
 * Deploy CertificateRegistry to Polygon Amoy.
 *
 * Gated on Phase 1: do not run this until `npx hardhat test` passes.
 *
 *   npx hardhat run scripts/deploy.js --network amoy
 *
 * Writes deployment/amoy.json containing the address and ABI, which the Django
 * backend reads via BLOCKCHAIN_CONTRACT_ADDRESS / the checked-in ABI file.
 */
import { network } from "hardhat";
import { writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

async function main() {
  const { ethers } = await network.connect();

  const [deployer] = await ethers.getSigners();
  if (!deployer) {
    throw new Error(
      "No signer available. Set DEPLOYER_PRIVATE_KEY in blockchain/.env"
    );
  }

  const balance = await ethers.provider.getBalance(deployer.address);
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Balance:  ${ethers.formatEther(balance)} POL`);

  if (balance === 0n) {
    throw new Error(
      "Deployer has zero balance. Fund it from an Amoy faucet before deploying."
    );
  }

  const factory = await ethers.getContractFactory("CertificateRegistry");
  const contract = await factory.deploy();
  console.log("Deploying… waiting for confirmation");
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  const deployTx = contract.deploymentTransaction();

  console.log(`\nCertificateRegistry deployed to: ${address}`);
  console.log(`Deploy tx:  ${deployTx?.hash}`);
  console.log(`Explorer:   https://amoy.polygonscan.com/address/${address}`);

  // The constructor authorises the deployer; confirm before we call it done.
  const authorized = await contract.authorizedIssuers(deployer.address);
  console.log(`Deployer authorised as issuer: ${authorized}`);

  const artifactPath = join(
    __dirname,
    "..",
    "artifacts",
    "contracts",
    "CertificateRegistry.sol",
    "CertificateRegistry.json"
  );
  const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));

  const outDir = join(__dirname, "..", "deployment");
  mkdirSync(outDir, { recursive: true });
  writeFileSync(
    join(outDir, "amoy.json"),
    JSON.stringify(
      {
        network: "amoy",
        chainId: 80002,
        address,
        deployer: deployer.address,
        deployTxHash: deployTx?.hash ?? null,
        deployedAt: new Date().toISOString(),
        abi: artifact.abi,
      },
      null,
      2
    )
  );

  // The Django blockchain app loads this ABI at runtime.
  const abiDir = join(__dirname, "..", "..", "backend", "blockchain", "abi");
  mkdirSync(abiDir, { recursive: true });
  writeFileSync(
    join(abiDir, "CertificateRegistry.json"),
    JSON.stringify(artifact.abi, null, 2)
  );

  console.log("\nWrote blockchain/deployment/amoy.json");
  console.log("Wrote backend/blockchain/abi/CertificateRegistry.json");
  console.log("\nNow set in backend/.env:");
  console.log(`  BLOCKCHAIN_CONTRACT_ADDRESS=${address}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
