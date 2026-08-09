import React, { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { API_BASE_URL } from '../api/config';
import { CheckCircle, XCircle } from 'lucide-react';

export const VerifyEmailPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      return;
    }

    const verify = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/auth/verify-email/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
        });

        if (res.ok) {
          setStatus('success');
        } else {
          setStatus('error');
        }
      } catch {
        setStatus('error');
      }
    };

    verify();
  }, [token]);

  return (
    <div className="auth-page">
      <Card className="auth-card" style={{ textAlign: 'center' }}>
        {status === 'loading' && (
          <>
            <h1 className="auth-title">Verifying Email...</h1>
            <p className="auth-subtitle">Please wait while we verify your email address.</p>
          </>
        )}
        
        {status === 'success' && (
          <>
            <CheckCircle size={48} color="var(--color-success-500)" style={{ marginBottom: 'var(--spacing-4)', margin: '0 auto' }} />
            <h1 className="auth-title">Email Verified</h1>
            <p className="auth-subtitle">Your email address has been successfully verified.</p>
            <Link to="/login" className="button button-primary" style={{ display: 'block', marginTop: 'var(--spacing-6)' }}>
              Proceed to Sign In
            </Link>
          </>
        )}

        {status === 'error' && (
          <>
            <XCircle size={48} color="var(--color-danger-500)" style={{ marginBottom: 'var(--spacing-4)', margin: '0 auto' }} />
            <h1 className="auth-title">Verification Failed</h1>
            <p className="auth-subtitle">
              The verification link is invalid or has expired. Please try registering again or contact support.
            </p>
            <Link to="/register" className="button button-primary" style={{ display: 'block', marginTop: 'var(--spacing-6)' }}>
              Back to Registration
            </Link>
          </>
        )}
      </Card>
    </div>
  );
};
