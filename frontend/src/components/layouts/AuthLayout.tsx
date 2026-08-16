import React from 'react';
import { Outlet, Link, useNavigate } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../ui/Button';

export const AuthLayout: React.FC = () => {
  const { logout, organization } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="auth-layout">
      <header className="auth-header">
        <Link to="/dashboard" className="auth-brand">BCIP</Link>

        {/* Which account you are signed into. Without this an operator with
            access to more than one organisation cannot tell where they are. */}
        {organization && (
          <div className="auth-org">
            <span>Signed in as <strong>{organization.name}</strong></span>
          </div>
        )}

        <nav>
          <Button variant="outline" onClick={handleLogout}>
            <LogOut size={15} />
            Sign out
          </Button>
        </nav>
      </header>

      <main className="auth-main">
        <Outlet />
      </main>
    </div>
  );
};
