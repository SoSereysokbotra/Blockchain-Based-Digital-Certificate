import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { API_BASE_URL } from '../api/config';
import { AlertTriangle, CheckCircle } from 'lucide-react';

export const RegisterPage: React.FC = () => {
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    if (password.length < 10) newErrors.password = 'Password must be at least 10 characters.';
    if (password !== confirmPassword) newErrors.confirmPassword = 'Passwords do not match.';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    if (!validate()) return;

    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/auth/register/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password }),
      });

      if (res.status === 400) {
        const data = await res.json();
        const fieldErrors: Record<string, string> = {};
        for (const [key, val] of Object.entries(data)) {
          if (Array.isArray(val)) fieldErrors[key] = val[0];
          else if (typeof val === 'string') fieldErrors[key] = val;
        }
        setErrors(fieldErrors);
        return;
      }

      if (!res.ok) throw new Error('Registration failed');

      setIsSuccess(true);
    } catch {
      setGeneralError('An unexpected error occurred. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  if (isSuccess) {
    return (
      <div className="auth-page">
        <Card className="auth-card" style={{ textAlign: 'center' }}>
          <CheckCircle size={48} color="var(--color-success-500)" style={{ marginBottom: 'var(--spacing-4)' }} />
          <h1 className="auth-title">Registration Successful</h1>
          <p className="auth-subtitle">
            A verification code has been sent to <strong>{email}</strong>. Please check your email.
          </p>
          <Button onClick={() => navigate('/verify-email')} style={{ width: '100%', marginTop: 'var(--spacing-6)' }}>
            Verify Email
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <Card className="auth-card">
        <h1 className="auth-title">Create Account</h1>
        <p className="auth-subtitle">Register your organization</p>

        {generalError && (
          <div className="auth-error-banner">
            <AlertTriangle size={18} />
            <span>{generalError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          <Input label="Organization Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} required />
          <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} required />
          <Input label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} placeholder="Minimum 10 characters" required />
          <Input label="Confirm Password" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} error={errors.confirmPassword} required />
          <Button type="submit" isLoading={isLoading} style={{ width: '100%', marginTop: 'var(--spacing-4)' }}>
            Register
          </Button>
        </form>

        <div className="auth-links">
          <Link to="/login">Already have an account? Sign in</Link>
        </div>
      </Card>
    </div>
  );
};
