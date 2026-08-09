import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Lock, AlertTriangle } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { login, isLoading } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLocked, setIsLocked] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLocked(false);

    const result = await login(email, password);

    if (result.success) {
      navigate('/dashboard');
    } else {
      if (result.status === 423) {
        setIsLocked(true);
      }
      setError(result.error || 'Login failed.');
    }
  };

  return (
    <div className="auth-page">
      <Card className="auth-card">
        <h1 className="auth-title">Sign In</h1>
        <p className="auth-subtitle">Access your organization portal</p>

        {isLocked && (
          <div className="auth-lockout-banner">
            <Lock size={20} />
            <div>
              <strong>Account Locked</strong>
              <p>Too many failed attempts. Please try again in 30 minutes.</p>
            </div>
          </div>
        )}

        {error && !isLocked && (
          <div className="auth-error-banner">
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          <Input
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@organization.com"
            required
          />
          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••••"
            required
          />
          <Button type="submit" isLoading={isLoading} style={{ width: '100%', marginTop: 'var(--spacing-4)' }}>
            Sign In
          </Button>
        </form>

        <div className="auth-links">
          <Link to="/reset-password">Forgot password?</Link>
          <Link to="/register">Create an account</Link>
        </div>
      </Card>
    </div>
  );
};
