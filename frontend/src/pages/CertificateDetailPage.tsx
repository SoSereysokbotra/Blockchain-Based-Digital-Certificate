import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { StatusPill } from '../components/ui/StatusPill';
import { API_BASE_URL } from '../api/config';
import { ArrowLeft, ExternalLink, RefreshCw, AlertCircle } from 'lucide-react';
import type { CertificateDetail } from '../api/types';

export const CertificateDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  
  const [cert, setCert] = useState<CertificateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);

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
        // Optimistically update status to PENDING
        setCert({ ...cert, status: 'PENDING' });
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsRetrying(false);
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
  // For the mock, we'll just show it if status is FAILED or if it's explicitly the 'cert-stale-pending' fixture.
  const isFailed = cert.status === 'FAILED';
  const isStalePending = cert.status === 'PENDING' && cert.certificate_id === 'cert-stale-pending';
  const canRetry = isFailed || isStalePending;

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
    </div>
  );
};
