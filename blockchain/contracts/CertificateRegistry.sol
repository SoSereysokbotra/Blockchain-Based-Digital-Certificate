// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title CertificateRegistry
/// @notice Hash-anchoring registry for BCIP. Stores only a certificate's SHA-256
///         hash plus minimal metadata; all human-readable certificate content
///         lives off-chain in PostgreSQL (SRS 2.5, 7.1).
/// @dev    Certificates are keyed by `certIdHash` = keccak256(certificate_id).
///         A fixed 32-byte key is used instead of a `string` key because a
///         dynamic key costs materially more gas to store, and a `string` event
///         parameter cannot be usefully indexed (it is stored as its own hash),
///         so filtering logs by the readable ID would be impossible either way.
contract CertificateRegistry {
    struct CertificateRecord {
        bytes32 certHash;
        address issuer;
        uint256 issuedAt;
        bool revoked;
    }

    /// @notice Deployer; may authorise and de-authorise issuer addresses.
    address public immutable owner;

    /// @notice Addresses permitted to call `issueCertificate`.
    mapping(address => bool) public authorizedIssuers;

    /// @dev keccak256(certificate_id) => record.
    mapping(bytes32 => CertificateRecord) private certificates;

    event CertificateIssued(
        bytes32 indexed certIdHash,
        bytes32 certHash,
        address indexed issuer,
        uint256 issuedAt
    );
    event CertificateRevoked(bytes32 indexed certIdHash, address indexed issuer);
    event IssuerAuthorized(address indexed issuer);
    event IssuerDeauthorized(address indexed issuer);

    error NotOwner();
    error NotAuthorizedIssuer();
    error CertificateAlreadyExists();
    error CertificateNotFound();
    error NotOriginalIssuer();
    error AlreadyRevoked();
    error ZeroCertHash();
    error ZeroAddress();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyAuthorizedIssuer() {
        if (!authorizedIssuers[msg.sender]) revert NotAuthorizedIssuer();
        _;
    }

    /// @dev The deployer is authorised as an issuer so a single-organisation
    ///      deployment (SRS 2.6) works without a second transaction.
    constructor() {
        owner = msg.sender;
        authorizedIssuers[msg.sender] = true;
        emit IssuerAuthorized(msg.sender);
    }

    // ─── Issuer administration ────────────────────────────────────────────────

    function authorizeIssuer(address issuer) external onlyOwner {
        if (issuer == address(0)) revert ZeroAddress();
        authorizedIssuers[issuer] = true;
        emit IssuerAuthorized(issuer);
    }

    function deauthorizeIssuer(address issuer) external onlyOwner {
        authorizedIssuers[issuer] = false;
        emit IssuerDeauthorized(issuer);
    }

    // ─── Certificate lifecycle ────────────────────────────────────────────────

    /// @notice Anchor a certificate hash. Restricted to authorised issuers.
    /// @param certIdHash keccak256 of the off-chain certificate_id.
    /// @param certHash   SHA-256 of the certificate's canonical data (SRS 7.2.1).
    function issueCertificate(bytes32 certIdHash, bytes32 certHash)
        external
        onlyAuthorizedIssuer
    {
        if (certHash == bytes32(0)) revert ZeroCertHash();
        if (certificates[certIdHash].issuer != address(0)) {
            revert CertificateAlreadyExists();
        }

        certificates[certIdHash] = CertificateRecord({
            certHash: certHash,
            issuer: msg.sender,
            issuedAt: block.timestamp,
            revoked: false
        });

        emit CertificateIssued(certIdHash, certHash, msg.sender, block.timestamp);
    }

    /// @notice Mark a certificate revoked. Callable only by the address that
    ///         originally issued that specific certificate — not merely by any
    ///         authorised issuer (SRS 7.4).
    function revokeCertificate(bytes32 certIdHash) external {
        CertificateRecord storage record = certificates[certIdHash];

        if (record.issuer == address(0)) revert CertificateNotFound();
        if (record.issuer != msg.sender) revert NotOriginalIssuer();
        if (record.revoked) revert AlreadyRevoked();

        record.revoked = true;

        emit CertificateRevoked(certIdHash, msg.sender);
    }

    // ─── Reads ────────────────────────────────────────────────────────────────

    /// @notice Read a certificate record. Free `view` call — no gas, no signer.
    /// @dev    An unknown `certIdHash` returns the zero-value struct
    ///         `(0x00..00, address(0), 0, false)` rather than reverting. Callers
    ///         MUST treat `issuer == address(0)` as "not found"; a zero
    ///         `certHash` alone is not a safe existence check. The Django
    ///         integration relies on this exact shape.
    function getCertificate(bytes32 certIdHash)
        external
        view
        returns (CertificateRecord memory)
    {
        return certificates[certIdHash];
    }

    /// @notice Convenience existence check mirroring the rule documented above.
    function exists(bytes32 certIdHash) external view returns (bool) {
        return certificates[certIdHash].issuer != address(0);
    }
}
