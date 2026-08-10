import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { StatusPill } from '../components/ui/StatusPill';
import { Modal } from '../components/ui/Modal';
import { useToast } from '../context/ToastContext';
import { API_BASE_URL } from '../api/config';
import { ArrowLeft, ExternalLink, RefreshCw, AlertCircle, Ban } from 'lucide-react';
import type { CertificateDetail } from '../api/types';

export const CertificateDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { addToast } = useToast();
  
  const [cert, setCert] = useState<CertificateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);

  // Revocation modal state
  const [revokeModalOpen, setRevokeModalOpen] = useState(false);
  const [revokeReason, setRevokeReason] = useState('');
  const [revokeReasonError, setRevokeReasonError] = useState('');
  const [isRevoking, setIsRevoking] = useState(false);

  useEffect(() => {
    const fetchCert = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/certificates/${id}/`);
        if (res.status === 404) throw new Error('Certificate not found');
        if (!res.ok) throw new Error('Failed to fetch certificate');
        
        const data = await res.json() as CertificateDetail;
        setCert(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };
    
    if (id) fetchCert();
  }, [id]);

  const handleRetry = async () => {
    if (!cert) return;
    setIsRetrying(true);
    try {
      const res = await fetch(`${API_BASE_URL}/certificates/${cert.certificate_id}/retry/`, { method: 'POST' });
      if (res.ok) {
        setCert({ ...cert, status: 'PENDING' });
        addToast('info', 'Retry started — confirming on-chain…');
      }
    } catch {
      addToast('error', 'Failed to retry issuance.');
    } finally {
      setIsRetrying(false);
    }
  };

  const handleRevoke = async () => {
    if (!cert) return;

    if (!revokeReason.trim()) {
      setRevokeReasonError('A reason for revocation is required.');
      return;
    }

    setIsRevoking(true);
    try {
      const res = await fetch(`${API_BASE_URL}/certificates/${cert.certificate_id}/revoke/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: revokeReason })
      });

      if (res.ok) {
        setCert({ ...cert, status: 'REVOKED' });
        addToast('success', 'Certificate revoked successfully.');
        setRevokeModalOpen(false);
        setRevokeReason('');
      } else {
        addToast('error', 'Failed to revoke certificate.');
      }
    } catch {
      addToast('error', 'Failed to revoke certificate.');
    } finally {
      setIsRevoking(false);
    }
  };

  if (loading) return <div className="detail-page-loading">Loading...</div>;
  
  if (error || !cert) {
    return (
      <div className="detail-page-error">
        <AlertCircle size={32} />
        <h2>{error || 'Certificate not found'}</h2>
        <Button onClick={() => navigate('/dashboard')} style={{ marginTop: 'var(--spacing-4)' }}>
          Back to Dashboard
        </Button>
      </div>
    );
  }

  // Determine if it's a "stale" pending request to show the retry button.
  const isFailed = cert.status === 'FAILED';
  const isStalePending = cert.status === 'PENDING' && cert.certificate_id === 'cert-stale-pending';
  const canRetry = isFailed || isStalePending;

  // Can revoke if status is VALID or PENDING (per FR-3.4)
  const canRevoke = cert.status === 'VALID' || cert.status === 'PENDING';

  return (
    <div className="detail-page">
      <div className="detail-header">
        <Button variant="outline" onClick={() => navigate('/dashboard')} className="back-button">
          <ArrowLeft size={16} /> Back
        </Button>
        <div className="detail-header-actions">
          {canRetry && (
            <Button onClick={handleRetry} isLoading={isRetrying} className="retry-button">
              <RefreshCw size={16} style={{ marginRight: 'var(--spacing-2)' }} /> Retry Issuance
            </Button>
          )}
          {canRevoke && (
            <Button variant="outline" onClick={() => setRevokeModalOpen(true)} className="revoke-button">
              <Ban size={16} style={{ marginRight: 'var(--spacing-2)' }} /> Revoke
            </Button>
          )}
        </div>
      </div>

      <Card className="detail-card">
        <div className="detail-title-row">
          <div>
            <h1 className="detail-title">{cert.recipient_name}</h1>
            <p className="detail-subtitle">{cert.course_title}</p>
          </div>
          <StatusPill status={cert.status} />
        </div>

        <div className="detail-grid">
          <div className="detail-item">
            <label>Certificate ID</label>
            <span className="detail-value mono">{cert.certificate_id}</span>
          </div>
          <div className="detail-item">
            <label>Recipient Email</label>
            <span className="detail-value">{cert.recipient_email}</span>
          </div>
          <div className="detail-item">
            <label>Issue Date</label>
            <span className="detail-value">{cert.issue_date}</span>
          </div>
          <div className="detail-item">
            <label>Expiry Date</label>
            <span className="detail-value">{cert.expiry_date || 'None'}</span>
          </div>
        </div>

        <div className="detail-blockchain-section">
          <label>Blockchain Transaction</label>
          {cert.blockchain_tx_hash ? (
            <div className="blockchain-hash-container">
              <span className="detail-value mono">{cert.blockchain_tx_hash}</span>
              <a 
                href={`https://amoy.polygonscan.com/tx/${cert.blockchain_tx_hash}`} 
                target="_blank" 
                rel="noopener noreferrer"
                className="blockchain-explorer-link"
              >
                View on Polygonscan <ExternalLink size={14} />
              </a>
            </div>
          ) : (
            <span className="detail-value muted">Not available</span>
          )}
        </div>
      </Card>

      {/* Revocation Modal */}
      <Modal
        isOpen={revokeModalOpen}
        onClose={() => {
          setRevokeModalOpen(false);
          setRevokeReason('');
          setRevokeReasonError('');
        }}
        title="Revoke Certificate"
        footer={
          <div className="revoke-modal-footer">
            <Button variant="outline" onClick={() => {
              setRevokeModalOpen(false);
              setRevokeReason('');
              setRevokeReasonError('');
            }}>
              Cancel
            </Button>
            <Button onClick={handleRevoke} isLoading={isRevoking} className="revoke-confirm-btn">
              Confirm Revocation
            </Button>
          </div>
        }
      >
        <div className="revoke-modal-body">
          <p className="revoke-warning">
            This action is <strong>irreversible</strong>. Once revoked, the certificate's on-chain status will be permanently updated.
          </p>
          <div className="input-group">
            <label htmlFor="revoke-reason" className="input-label">
              Reason for Revocation <span style={{ color: 'var(--color-danger-500)' }}>*</span>
            </label>
            <textarea
              id="revoke-reason"
              className={`input-field revoke-textarea ${revokeReasonError ? 'error' : ''}`}
              value={revokeReason}
              onChange={(e) => {
                setRevokeReason(e.target.value);
                if (revokeReasonError) setRevokeReasonError('');
              }}
              placeholder="e.g. Plagiarism detected, issued in error…"
              rows={3}
            />
            {revokeReasonError && (
              <span className="input-error-text">{revokeReasonError}</span>
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
};
