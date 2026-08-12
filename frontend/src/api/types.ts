export type CertificateStatus = 'PENDING' | 'VALID' | 'EXPIRED' | 'REVOKED' | 'FAILED';
export type VerificationOutcome = 'VALID' | 'EXPIRED' | 'REVOKED' | 'TAMPERED' | 'NOT_FOUND' | 'UNVERIFIED';

export interface LoginResponse {
  access_token: string;
}

export interface ErrorResponse {
  detail?: string;
  [key: string]: string[] | string | undefined;
}

export interface CreateCertificateRequest {
  recipient_name: string;
  recipient_email: string;
  course_title: string;
  issue_date: string;
  expiry_date: string | null;
}

export interface CreateCertificateResponse {
  certificate_id: string;
  status: CertificateStatus;
  pdf_url: string;
}

export interface CertificateListItem {
  certificate_id: string;
  recipient_name: string;
  issue_date: string;
  status: CertificateStatus;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface CertificateDetail {
  certificate_id: string;
  recipient_name: string;
  recipient_email: string;
  course_title: string;
  issue_date: string;
  expiry_date: string | null;
  status: CertificateStatus;
  blockchain_tx_hash: string | null;
  pdf_url: string;
}

export interface RevokeCertificateRequest {
  reason: string;
}

export interface VerificationResult {
  certificate_id: string;
  recipient_name: string;
  course_title: string;
  issue_date: string;
  status: VerificationOutcome;
  blockchain_tx_hash: string | null;
  revocation_reason: string | null;
  warning?: string;
  detail?: string;
}
