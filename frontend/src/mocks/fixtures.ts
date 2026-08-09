import type { CertificateDetail, VerificationResult } from '../api/types';

export const mockCertificates: CertificateDetail[] = [
  {
    certificate_id: 'cert-1-valid',
    recipient_name: 'Alice Smith',
    recipient_email: 'alice@example.com',
    course_title: 'Blockchain Fundamentals',
    issue_date: '2023-10-01',
    expiry_date: null,
    status: 'VALID',
    blockchain_tx_hash: '0x123abc456def',
    pdf_url: 'https://example.com/certs/cert-1-valid.pdf'
  },
  {
    certificate_id: 'cert-2-pending',
    recipient_name: 'Bob Jones',
    recipient_email: 'bob@example.com',
    course_title: 'Advanced Cryptography',
    issue_date: '2023-10-15',
    expiry_date: null,
    status: 'PENDING',
    blockchain_tx_hash: null,
    pdf_url: 'https://example.com/certs/cert-2-pending.pdf'
  },
  {
    certificate_id: 'cert-3-expired',
    recipient_name: 'Charlie Brown',
    recipient_email: 'charlie@example.com',
    course_title: 'Smart Contract Auditing',
    issue_date: '2021-01-01',
    expiry_date: '2022-01-01',
    status: 'EXPIRED',
    blockchain_tx_hash: '0x999ccc',
    pdf_url: 'https://example.com/certs/cert-3-expired.pdf'
  },
  {
    certificate_id: 'cert-4-revoked',
    recipient_name: 'Diana Prince',
    recipient_email: 'diana@example.com',
    course_title: 'DeFi Engineering',
    issue_date: '2022-05-01',
    expiry_date: null,
    status: 'REVOKED',
    blockchain_tx_hash: '0xabc123',
    pdf_url: 'https://example.com/certs/cert-4-revoked.pdf'
  },
  {
    certificate_id: 'cert-5-failed',
    recipient_name: 'Eve Adams',
    recipient_email: 'eve@example.com',
    course_title: 'Web3 Development',
    issue_date: '2023-10-20',
    expiry_date: null,
    status: 'FAILED',
    blockchain_tx_hash: null,
    pdf_url: 'https://example.com/certs/cert-5-failed.pdf'
  }
];

export const mockVerificationResults: Record<string, VerificationResult> = {
  'cert-1-valid': {
    certificate_id: 'cert-1-valid',
    recipient_name: 'Alice Smith',
    course_title: 'Blockchain Fundamentals',
    issue_date: '2023-10-01',
    status: 'VALID',
    blockchain_tx_hash: '0x123abc456def',
    revocation_reason: null
  },
  'cert-3-expired': {
    certificate_id: 'cert-3-expired',
    recipient_name: 'Charlie Brown',
    course_title: 'Smart Contract Auditing',
    issue_date: '2021-01-01',
    status: 'EXPIRED',
    blockchain_tx_hash: '0x999ccc',
    revocation_reason: null
  },
  'cert-4-revoked': {
    certificate_id: 'cert-4-revoked',
    recipient_name: 'Diana Prince',
    course_title: 'DeFi Engineering',
    issue_date: '2022-05-01',
    status: 'REVOKED',
    blockchain_tx_hash: '0xabc123',
    revocation_reason: 'Plagiarism detected'
  },
  'cert-6-tampered': {
    certificate_id: 'cert-6-tampered',
    recipient_name: 'Frank Miller',
    course_title: 'Ethereum Architecture',
    issue_date: '2023-01-01',
    status: 'TAMPERED',
    blockchain_tx_hash: '0x444fff',
    revocation_reason: null
  }
};
