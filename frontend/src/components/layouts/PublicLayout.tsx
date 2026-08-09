import React from 'react';
import { Outlet, Link } from 'react-router-dom';
import { ToastContainer } from '../ui/Toast';

export const PublicLayout: React.FC = () => {
  return (
    <div className="public-layout">
      <header className="public-header">
        <Link to="/verify" className="public-brand" style={{ color: 'white', textDecoration: 'none' }}>BCIP Verification</Link>
        <p className="public-subtitle">Blockchain-Based Digital Certificate Issuing Platform</p>
      </header>
      <main className="public-main">
        <Outlet />
      </main>
      <ToastContainer>
        {/* Toasts will be rendered here via context later */}
      </ToastContainer>
    </div>
  );
};
