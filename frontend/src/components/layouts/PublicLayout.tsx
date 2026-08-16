import React from 'react';
import { Outlet, Link } from 'react-router-dom';

export const PublicLayout: React.FC = () => {
  return (
    <div className="public-layout">
      <header className="public-header">
        <Link to="/verify" className="public-brand">BCIP Verification</Link>
        <p className="public-subtitle">
          Check whether a certificate is genuine — no account required
        </p>
      </header>

      <main className="public-main">
        <Outlet />
      </main>
    </div>
  );
};
