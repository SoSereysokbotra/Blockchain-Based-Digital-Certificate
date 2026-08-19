import React, { useState } from 'react';
import { useLocation, Link, useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import api from '../api/client';
import { useToast } from '../context/ToastContext';
import { AlertTriangle, CheckCircle } from 'lucide-react';

export const VerifyEmailPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { addToast } = useToast();

  // If we came from the registration page, the email might be in state
  const stateEmail = location.state?.email || '';

  const [email, setEmail] = useState(stateEmail);
  const [code, setCode] = useState('');
  
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email || !code) {
      setError('Please provide both email and verification code.');
      return;
    }

    setIsLoading(true);

    try {
      await api.post('/auth/verify-email/', { email, code });
      setIsSuccess(true);
      addToast('success', 'Email verified successfully! You can now log in.');
      setTimeout(() => navigate('/login'), 3000);
    } catch (err: any) {
      if (err.response?.status === 400) {
        setError(err.response.data?.detail || 'Invalid or expired verification code.');
      } else {
        setError('An unexpected error occurred. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    if (!email) {
      setError('Please enter your email to resend the code.');
      return;
    }
    setError(null);
    try {
      await api.post('/auth/resend-email-verification/', { email });
      addToast('success', 'A new verification code has been sent.');
    } catch {
      setError('Failed to resend code. Please try again later.');
    }
  };

  if (isSuccess) {
    return (
      <div className="auth-page">
        <Card className="auth-card" style={{ textAlign: 'center' }}>
          <CheckCircle size={48} color="var(--color-success-500)" style={{ marginBottom: 'var(--spacing-4)', margin: '0 auto' }} />
          <h1 className="auth-title">Email Verified</h1>
          <p className="auth-subtitle">Your email address has been successfully verified.</p>
          <Link to="/login" className="button button-primary" style={{ display: 'block', marginTop: 'var(--spacing-6)' }}>
            Proceed to Sign In
          </Link>
        </Card>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <Card className="auth-card">
        <h1 className="auth-title">Verify Email</h1>
        
        {error && (
          <div className="auth-error-banner" style={{ marginTop: 'var(--spacing-4)' }}>
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleVerify} className="auth-form" style={{ marginTop: 'var(--spacing-6)' }}>
          <p className="auth-subtitle" style={{ marginBottom: 'var(--spacing-4)' }}>
            Enter the 6-digit verification code sent to your email.
          </p>
          
          <Input 
            label="Email" 
            type="email" 
            value={email} 
            onChange={(e) => setEmail(e.target.value)} 
            required 
          />
          
          <Input 
            label="Verification Code" 
            value={code} 
            onChange={(e) => setCode(e.target.value)} 
            required 
            placeholder="e.g. 123456"
          />
          
          <Button type="submit" isLoading={isLoading} style={{ width: '100%', marginTop: 'var(--spacing-4)' }}>
            Verify Email
          </Button>
          
          <Button type="button" variant="outline" onClick={handleResend} style={{ width: '100%', marginTop: 'var(--spacing-2)' }}>
            Resend Code
          </Button>
        </form>

        <div className="auth-links">
          <Link to="/login">Back to Sign In</Link>
        </div>
      </Card>
    </div>
  );
};
