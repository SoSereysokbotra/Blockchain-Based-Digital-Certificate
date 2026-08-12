import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { StatusPill } from '../components/ui/StatusPill';
import { Search, ExternalLink, AlertTriangle } from 'lucide-react';
import { useToast } from '../context/ToastContext';
import api from '../api/client';
import type { VerificationResult } from '../api/types';

export const VerificationPage: React.FC = () => {
  const { certId } = useParams<{ certId: string }>();
  const navigate = useNavigate();
  const { addToast } = useToast();
  
  const [searchInput, setSearchInput] = useState(certId || '');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (certId) {
      handleSearch(certId);
    } else {
      setResult(null);
      setError(null);
    }
  }, [certId]);

  const handleSearch = async (idToSearch: string) => {
    if (!idToSearch.trim()) return;
    
    setLoading(true);
    setError(null);
    setResult(null);
    
    try {
      const res = await api.get<VerificationResult>(`/public/verify/${encodeURIComponent(idToSearch.trim())}/`);
      setResult(res.data);
      
      if (res.data.status === 'VALID') {
        addToast('success', 'Certificate is valid and verified on-chain.');
      } else {
        addToast('error', `Certificate status is ${res.data.status}.`);
      }
    } catch (err: any) {
      if (err.response?.status === 404) {
        setError('Certificate not found. Please check the ID and try again.');
      } else if (err.response?.status === 429) {
        setError('Too many requests. Please try again later.');
      } else {
        setError('An unexpected error occurred during verification.');
      }
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      navigate(`/verify/${encodeURIComponent(searchInput.trim())}`);
    }
  };

  return (
    <div className="verification-page">
      <Card className="verification-search-card">
        <h1 style={{ marginBottom: 'var(--spacing-6)', color: 'var(--color-primary-900)' }}>Verify a Certificate</h1>
        <form onSubmit={onSubmit} className="verification-search-form">
          <Input 
            label="Certificate ID" 
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="e.g. cert-1-valid"
            required
          />
          <Button type="submit" isLoading={loading} style={{ marginTop: 'var(--spacing-6)' }}>
            <Search size={18} style={{ marginRight: 'var(--spacing-2)' }} />
            Verify
          </Button>
        </form>
      </Card>

      {error && (
        <Card className="verification-error-card">
          <AlertTriangle size={32} color="var(--color-warning-500)" style={{ marginBottom: 'var(--spacing-4)' }} />
          <h2 style={{ color: 'var(--color-neutral-900)', marginBottom: 'var(--spacing-2)' }}>Verification Failed</h2>
          <p style={{ color: 'var(--color-neutral-600)' }}>{error}</p>
        </Card>
      )}

      {result && (
        <Card className="verification-result-card">
          <div className="verification-result-header">
            <h2 style={{ margin: 0, color: 'var(--color-neutral-900)' }}>Verification Result</h2>
            <StatusPill status={result.status} />
          </div>

          {(result.status === 'TAMPERED' || result.status === 'REVOKED' || result.status === 'UNVERIFIED') && (
            <div className="verification-warning">
              <AlertTriangle size={24} />
              <div>
                <strong>Warning: {result.warning || 'This certificate is not valid.'}</strong>
                {result.revocation_reason && <p style={{ margin: 'var(--spacing-1) 0 0 0' }}>Reason: {result.revocation_reason}</p>}
                {result.detail && <p style={{ margin: 'var(--spacing-1) 0 0 0' }}>Detail: {result.detail}</p>}
              </div>
            </div>
          )}

          <div className="verification-details">
            <div className="detail-group">
              <label>Recipient Name</label>
              <p>{result.recipient_name}</p>
            </div>
            <div className="detail-group">
              <label>Course Title</label>
              <p>{result.course_title}</p>
            </div>
            <div className="detail-group">
              <label>Issue Date</label>
              <p>{result.issue_date}</p>
            </div>
            <div className="detail-group">
              <label>Certificate ID</label>
              <p style={{ fontFamily: 'monospace' }}>{result.certificate_id}</p>
            </div>
          </div>

          {result.blockchain_tx_hash && (
            <div className="verification-blockchain">
              <label>Blockchain Proof</label>
              <a 
                href={`https://amoy.polygonscan.com/tx/${result.blockchain_tx_hash}`} 
                target="_blank" 
                rel="noopener noreferrer"
                className="blockchain-link"
              >
                View Transaction on Polygonscan
                <ExternalLink size={14} style={{ marginLeft: 'var(--spacing-1)' }} />
              </a>
            </div>
          )}
        </Card>
      )}
    </div>
  );
};
