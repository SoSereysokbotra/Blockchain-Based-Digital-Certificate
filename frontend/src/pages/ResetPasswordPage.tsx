import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { CodeInput } from '../components/ui/CodeInput';
import { FormStepper } from '../components/ui/FormStepper';
import api from '../api/client';
import { useToast } from '../context/ToastContext';
import { AlertTriangle, CheckCircle } from 'lucide-react';

export const ResetPasswordPage: React.FC = () => {
  const [step, setStep] = useState(0);
  const steps = ['Email', 'Verify Code', 'New Password'];
  const navigate = useNavigate();
  const { addToast } = useToast();

  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleRequestCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await api.post('/auth/request-password-reset/', { email });
      setStep(1);
    } catch {
      setError('An error occurred. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await api.post('/auth/verify-password-reset/', { email, code });
      setStep(2);
    } catch (err: any) {
      setError('Invalid or expired code');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password.length < 10) {
      setError('Password must be at least 10 characters.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setIsLoading(true);
    try {
      await api.post('/auth/reset-password/', { email, code, new_password: password });
      addToast('success', 'Password reset successfully. You can now log in.');
      navigate('/login');
    } catch (error: any) {
      if (error.response?.status === 400) {
        setError('Invalid code or password does not meet criteria.');
      } else {
        setError('An error occurred. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <Card className="auth-card">
        <h1 className="auth-title">Reset Password</h1>
        
        {step < 3 && <FormStepper steps={steps} currentStep={step} />}

        {error && (
          <div className="auth-error-banner" style={{ marginTop: 'var(--spacing-4)' }}>
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
        )}

        {step === 0 && (
          <form onSubmit={handleRequestCode} className="auth-form" style={{ marginTop: 'var(--spacing-6)' }}>
            <p className="auth-subtitle" style={{ marginBottom: 'var(--spacing-4)' }}>
              Enter your email address and we'll send you a code to reset your password.
            </p>
            <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <Button type="submit" isLoading={isLoading} style={{ width: '100%', marginTop: 'var(--spacing-4)' }}>
              Send Reset Code
            </Button>
          </form>
        )}

        {step === 1 && (
          <form onSubmit={handleVerifyCode} className="auth-form" style={{ marginTop: 'var(--spacing-6)' }}>
             <p className="auth-subtitle" style={{ marginBottom: 'var(--spacing-4)' }}>
              Enter the verification code sent to <strong>{email}</strong>.
            </p>
            <CodeInput
              value={code}
              onChange={setCode}
              error={!!error}
              disabled={isLoading}
            />
            <Button type="submit" isLoading={isLoading} style={{ width: '100%', marginTop: 'var(--spacing-4)' }}>
              Verify Code
            </Button>
            <Button type="button" variant="outline" onClick={() => setStep(0)} style={{ width: '100%', marginTop: 'var(--spacing-2)' }}>
              Back
            </Button>
          </form>
        )}

        {step === 2 && (
          <form onSubmit={handleSetPassword} className="auth-form" style={{ marginTop: 'var(--spacing-6)' }}>
            <p className="auth-subtitle" style={{ marginBottom: 'var(--spacing-4)' }}>
              Create a new strong password for your account.
            </p>
            <Input label="New Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Minimum 10 characters" required />
            <Input label="Confirm New Password" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
            <Button type="submit" isLoading={isLoading} style={{ width: '100%', marginTop: 'var(--spacing-4)' }}>
              Reset Password
            </Button>
          </form>
        )}

        {step === 3 && (
          <div style={{ textAlign: 'center', marginTop: 'var(--spacing-6)' }}>
             <CheckCircle size={48} color="var(--color-success-500)" style={{ marginBottom: 'var(--spacing-4)' }} />
             <h2 style={{ marginBottom: 'var(--spacing-2)', color: 'var(--color-neutral-900)' }}>Password Reset Complete</h2>
             <p className="auth-subtitle" style={{ marginBottom: 'var(--spacing-6)' }}>
               Your password has been successfully reset. You can now log in with your new password.
             </p>
             <Link to="/login" className="button button-primary" style={{ display: 'block' }}>
                Sign In
             </Link>
          </div>
        )}

        {step === 0 && (
          <div className="auth-links">
            <Link to="/login">Back to Sign In</Link>
          </div>
        )}
      </Card>
    </div>
  );
};
