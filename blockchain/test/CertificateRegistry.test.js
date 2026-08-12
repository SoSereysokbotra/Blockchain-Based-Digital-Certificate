/**
 * CertificateRegistry unit tests (Implementation Plan, Phase 1).
 *
 * These run entirely on Hardhat's in-memory chain: no testnet, no faucet, no
 * gas cost, no network access. The point of running them before deployment is
 * that an access-control bug is effectively unfixable once the contract is on
 * Amoy — the address is baked into the backend config and every already-issued
 * certificate is anchored against it.
 *
 *   npx hardhat test
 */
import { expect } from "chai";
import { network } from "hardhat";

const { ethers } = await network.getOrCreate("default");

// keccak256 of an off-chain certificate_id — exactly what the Django
// blockchain app computes via Web3.keccak(text=certificate_id).
const idHash = (certId) => ethers.keccak256(ethers.toUtf8Bytes(certId));

// Stand-in for sha256(canonical(cert)) from certificates/hashing.py.
const CERT_HASH_A =
  "0x1111111111111111111111111111111111111111111111111111111111111111";
const CERT_HASH_B =
  "0x2222222222222222222222222222222222222222222222222222222222222222";
const ZERO_BYTES32 = ethers.ZeroHash;

describe("CertificateRegistry", function () {
  let registry;
  let owner; // deploys; auto-authorised issuer
  let issuer2; // second authorised issuer
  let outsider; // never authorised
  let CERT_A;

  beforeEach(async function () {
    [owner, issuer2, outsider] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("CertificateRegistry");
    registry = await Factory.deploy();
    await registry.waitForDeployment();
    CERT_A = idHash("CERT-A1B2C3D4E5F6");
  });

  // ─── Deployment ───────────────────────────────────────────────────────────

  describe("deployment", function () {
    it("sets the deployer as owner", async function () {
      expect(await registry.owner()).to.equal(owner.address);
    });

    it("authorises the deployer as an issuer", async function () {
      expect(await registry.authorizedIssuers(owner.address)).to.equal(true);
    });

    it("does not authorise anybody else", async function () {
      expect(await registry.authorizedIssuers(outsider.address)).to.equal(false);
    });
  });

  // ─── Issuer administration ────────────────────────────────────────────────

  describe("issuer administration", function () {
    it("lets the owner authorise a new issuer", async function () {
      await expect(registry.authorizeIssuer(issuer2.address))
        .to.emit(registry, "IssuerAuthorized")
        .withArgs(issuer2.address);
      expect(await registry.authorizedIssuers(issuer2.address)).to.equal(true);
    });

    it("reverts when a non-owner tries to authorise an issuer", async function () {
      await expect(
        registry.connect(outsider).authorizeIssuer(outsider.address)
      ).to.be.revertedWithCustomError(registry, "NotOwner");
    });

    it("lets the owner de-authorise an issuer", async function () {
      await registry.authorizeIssuer(issuer2.address);
      await expect(registry.deauthorizeIssuer(issuer2.address))
        .to.emit(registry, "IssuerDeauthorized")
        .withArgs(issuer2.address);
      expect(await registry.authorizedIssuers(issuer2.address)).to.equal(false);
    });

    it("rejects the zero address as an issuer", async function () {
      await expect(
        registry.authorizeIssuer(ethers.ZeroAddress)
      ).to.be.revertedWithCustomError(registry, "ZeroAddress");
    });
  });

  // ─── issueCertificate ─────────────────────────────────────────────────────

  describe("issueCertificate", function () {
    it("succeeds for an authorised issuer with a fresh certIdHash", async function () {
      await registry.issueCertificate(CERT_A, CERT_HASH_A);

      const record = await registry.getCertificate(CERT_A);
      expect(record.certHash).to.equal(CERT_HASH_A);
      expect(record.issuer).to.equal(owner.address);
      expect(record.revoked).to.equal(false);
      expect(record.issuedAt).to.be.greaterThan(0n);
    });

    it("reverts when called by a non-authorised address", async function () {
      await expect(
        registry.connect(outsider).issueCertificate(CERT_A, CERT_HASH_A)
      ).to.be.revertedWithCustomError(registry, "NotAuthorizedIssuer");
    });

    it("reverts when the same certIdHash is issued twice", async function () {
      await registry.issueCertificate(CERT_A, CERT_HASH_A);
      await expect(
        registry.issueCertificate(CERT_A, CERT_HASH_B)
      ).to.be.revertedWithCustomError(registry, "CertificateAlreadyExists");
    });

    it("reverts on a duplicate even from a different authorised issuer", async function () {
      await registry.authorizeIssuer(issuer2.address);
      await registry.issueCertificate(CERT_A, CERT_HASH_A);
      await expect(
        registry.connect(issuer2).issueCertificate(CERT_A, CERT_HASH_B)
      ).to.be.revertedWithCustomError(registry, "CertificateAlreadyExists");
    });

    it("rejects a zero certHash", async function () {
      await expect(
        registry.issueCertificate(CERT_A, ZERO_BYTES32)
      ).to.be.revertedWithCustomError(registry, "ZeroCertHash");
    });

    it("emits CertificateIssued with the correct indexed parameters", async function () {
      const tx = await registry.issueCertificate(CERT_A, CERT_HASH_A);
      const receipt = await tx.wait();
      const block = await ethers.provider.getBlock(receipt.blockNumber);

      await expect(tx)
        .to.emit(registry, "CertificateIssued")
        .withArgs(CERT_A, CERT_HASH_A, owner.address, block.timestamp);
    });

    it("is filterable by the indexed certIdHash", async function () {
      const CERT_B = idHash("CERT-999999999999");
      await registry.issueCertificate(CERT_A, CERT_HASH_A);
      await registry.issueCertificate(CERT_B, CERT_HASH_B);

      // This is the concrete payoff of a bytes32 key over a string key: the
      // readable ID could never be recovered from an indexed string topic.
      const logs = await registry.queryFilter(
        registry.filters.CertificateIssued(CERT_B)
      );
      expect(logs).to.have.lengthOf(1);
      expect(logs[0].args.certHash).to.equal(CERT_HASH_B);
    });

    it("keeps separate records for different certIdHashes", async function () {
      const CERT_B = idHash("CERT-999999999999");
      await registry.authorizeIssuer(issuer2.address);
      await registry.issueCertificate(CERT_A, CERT_HASH_A);
      await registry.connect(issuer2).issueCertificate(CERT_B, CERT_HASH_B);

      expect((await registry.getCertificate(CERT_A)).issuer).to.equal(owner.address);
      expect((await registry.getCertificate(CERT_B)).issuer).to.equal(issuer2.address);
    });
  });

  // ─── revokeCertificate ────────────────────────────────────────────────────

  describe("revokeCertificate", function () {
    beforeEach(async function () {
      await registry.issueCertificate(CERT_A, CERT_HASH_A);
    });

    it("succeeds when called by the original issuer", async function () {
      await registry.revokeCertificate(CERT_A);
      expect((await registry.getCertificate(CERT_A)).revoked).to.equal(true);
    });

    it("reverts when called by an unauthorised outsider", async function () {
      await expect(
        registry.connect(outsider).revokeCertificate(CERT_A)
      ).to.be.revertedWithCustomError(registry, "NotOriginalIssuer");
    });

    /**
     * The single most safety-critical assertion in the system (SRS 7.4):
     * being an authorised issuer must NOT be enough to revoke someone else's
     * certificate. Only the address that issued that specific certificate may
     * revoke it. Without this, any onboarded organisation could invalidate a
     * competitor's credentials.
     */
    it("reverts when called by a DIFFERENT authorised issuer", async function () {
      await registry.authorizeIssuer(issuer2.address);
      expect(await registry.authorizedIssuers(issuer2.address)).to.equal(true);

      await expect(
        registry.connect(issuer2).revokeCertificate(CERT_A)
      ).to.be.revertedWithCustomError(registry, "NotOriginalIssuer");

      expect((await registry.getCertificate(CERT_A)).revoked).to.equal(false);
    });

    it("reverts when called by the owner if the owner did not issue it", async function () {
      const CERT_B = idHash("CERT-OWNEDBYISSUER2");
      await registry.authorizeIssuer(issuer2.address);
      await registry.connect(issuer2).issueCertificate(CERT_B, CERT_HASH_B);

      // Ownership of the registry confers no authority over another issuer's
      // certificates.
      await expect(
        registry.revokeCertificate(CERT_B)
      ).to.be.revertedWithCustomError(registry, "NotOriginalIssuer");
    });

    it("reverts for a certIdHash that was never issued", async function () {
      await expect(
        registry.revokeCertificate(idHash("CERT-NEVEREXISTED"))
      ).to.be.revertedWithCustomError(registry, "CertificateNotFound");
    });

    it("reverts when revoking an already-revoked certificate", async function () {
      await registry.revokeCertificate(CERT_A);
      await expect(
        registry.revokeCertificate(CERT_A)
      ).to.be.revertedWithCustomError(registry, "AlreadyRevoked");
    });

    it("emits CertificateRevoked with the correct indexed parameters", async function () {
      await expect(registry.revokeCertificate(CERT_A))
        .to.emit(registry, "CertificateRevoked")
        .withArgs(CERT_A, owner.address);
    });

    it("leaves certHash, issuer and issuedAt untouched", async function () {
      const before = await registry.getCertificate(CERT_A);
      await registry.revokeCertificate(CERT_A);
      const after = await registry.getCertificate(CERT_A);

      // Verification still needs to compare against the original hash after
      // revocation, so revoking must not disturb the anchor.
      expect(after.certHash).to.equal(before.certHash);
      expect(after.issuer).to.equal(before.issuer);
      expect(after.issuedAt).to.equal(before.issuedAt);
    });

    it("still permits revocation after the issuer is de-authorised", async function () {
      await registry.authorizeIssuer(issuer2.address);
      const CERT_B = idHash("CERT-ISSUEDTHENDEAUTH");
      await registry.connect(issuer2).issueCertificate(CERT_B, CERT_HASH_B);

      await registry.deauthorizeIssuer(issuer2.address);

      // Losing issuing rights must not strand certificates as un-revokable.
      await registry.connect(issuer2).revokeCertificate(CERT_B);
      expect((await registry.getCertificate(CERT_B)).revoked).to.equal(true);
    });
  });

  // ─── getCertificate ───────────────────────────────────────────────────────

  describe("getCertificate", function () {
    it("returns the correct struct fields for an issued certificate", async function () {
      const tx = await registry.issueCertificate(CERT_A, CERT_HASH_A);
      const receipt = await tx.wait();
      const block = await ethers.provider.getBlock(receipt.blockNumber);

      const record = await registry.getCertificate(CERT_A);
      expect(record.certHash).to.equal(CERT_HASH_A);
      expect(record.issuer).to.equal(owner.address);
      expect(record.issuedAt).to.equal(BigInt(block.timestamp));
      expect(record.revoked).to.equal(false);
    });

    /**
     * Documents the exact default the Django integration (Phase 5/7) relies on.
     * An unknown key does NOT revert — it returns the zero-value struct, so
     * `issuer == address(0)` is the existence test. A zero certHash alone is
     * not safe to test on, because issueCertificate rejects a zero certHash and
     * therefore a real record can never carry one.
     */
    it("returns the zero-value struct for a certIdHash that was never issued", async function () {
      const record = await registry.getCertificate(idHash("CERT-DOESNOTEXIST"));

      expect(record.certHash).to.equal(ZERO_BYTES32);
      expect(record.issuer).to.equal(ethers.ZeroAddress);
      expect(record.issuedAt).to.equal(0n);
      expect(record.revoked).to.equal(false);
    });

    it("is a free view call requiring no signer", async function () {
      await registry.issueCertificate(CERT_A, CERT_HASH_A);

      // staticCall proves it costs no gas and needs no transaction — this is
      // how the public verification endpoint reads the chain.
      const record = await registry.getCertificate.staticCall(CERT_A);
      expect(record.certHash).to.equal(CERT_HASH_A);
    });

    it("exists() agrees with the documented issuer != 0 rule", async function () {
      expect(await registry.exists(CERT_A)).to.equal(false);
      await registry.issueCertificate(CERT_A, CERT_HASH_A);
      expect(await registry.exists(CERT_A)).to.equal(true);
    });
  });

  // ─── Integration-shaped checks ────────────────────────────────────────────

  describe("tamper evidence", function () {
    it("stores a hash that differs when any source field differs", async function () {
      // Mirrors what certificates/hashing.py produces before and after an
      // attacker edits the recipient name in PostgreSQL.
      const original = ethers.sha256(
        ethers.toUtf8Bytes('{"courseTitle":"Solidity 101","recipientName":"Alice"}')
      );
      const tampered = ethers.sha256(
        ethers.toUtf8Bytes('{"courseTitle":"Solidity 101","recipientName":"Mallory"}')
      );

      await registry.issueCertificate(CERT_A, original);
      const onChain = (await registry.getCertificate(CERT_A)).certHash;

      expect(onChain).to.equal(original);
      expect(onChain).to.not.equal(tampered);
    });

    it("has no function that can overwrite an anchored certHash", async function () {
      await registry.issueCertificate(CERT_A, CERT_HASH_A);

      const mutating = registry.interface.fragments
        .filter((f) => f.type === "function")
        .filter((f) => f.stateMutability !== "view" && f.stateMutability !== "pure")
        .map((f) => f.name);

      // Only these three may write state. Anything else appearing here means
      // someone added a way to mutate an anchor, defeating tamper evidence.
      expect(mutating.sort()).to.deep.equal([
        "authorizeIssuer",
        "deauthorizeIssuer",
        "issueCertificate",
        "revokeCertificate",
      ].sort());
    });
  });
});
