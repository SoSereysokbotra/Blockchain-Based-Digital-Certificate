// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract CertificateRegistry {
    struct CertificateRecord {
        bytes32 certHash;
        address issuer;
        uint256 issuedAt;
        bool revoked;
    }

    mapping(string => CertificateRecord) private certificates;
    
    event CertificateIssued(string certId, bytes32 certHash, address issuer);
    event CertificateRevoked(string certId);

    function issueCertificate(string memory certId, bytes32 certHash) public {
        require(certificates[certId].issuer == address(0), "Certificate already exists");
        
        certificates[certId] = CertificateRecord({
            certHash: certHash,
            issuer: msg.sender,
            issuedAt: block.timestamp,
            revoked: false
        });
        
        emit CertificateIssued(certId, certHash, msg.sender);
    }

    function revokeCertificate(string memory certId) public {
        require(certificates[certId].issuer != address(0), "Certificate does not exist");
        require(certificates[certId].issuer == msg.sender, "Only the issuer can revoke");
        require(!certificates[certId].revoked, "Certificate is already revoked");
        
        certificates[certId].revoked = true;
        
        emit CertificateRevoked(certId);
    }

    function getCertificate(string memory certId) public view returns (CertificateRecord memory) {
        return certificates[certId];
    }
}
