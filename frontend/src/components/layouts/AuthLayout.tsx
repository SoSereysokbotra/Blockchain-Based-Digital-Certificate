import React from 'react';
import { Outlet, Link, useNavigate } from 'react-router-dom';
import { ToastContainer } from '../ui/Toast';
import { useAuth } from '../../context/AuthContext';
import { LogOut } from 'lucide-react';
import { Button } from '../ui/Button';

export const AuthLayout: React.FC = () => {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="auth-layout">
      <header className="auth-header">
        <Link to="/dashboard" className="auth-brand">BCIP Portal</Link>
        <nav>
          <Button variant="outline" onClick={handleLogout} style={{ padding: 'var(--spacing-2) var(--spacing-4)' }}>
            <LogOut size={16} style={{ marginRight: 'var(--spacing-2)' }} />
            Sign Out
          </Button>
        </nav>
      </header>
      <main className="auth-main">
        <Outlet />
      </main>
      <ToastContainer>
        {/* Toasts will be rendered here via context later */}
      </ToastContainer>
    </div>
  );
};
