import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { AuthLayout } from './components/layouts/AuthLayout';
import { PublicLayout } from './components/layouts/PublicLayout';
import { ProtectedRoute } from './components/layouts/ProtectedRoute';
import { VerificationPage } from './pages/VerificationPage';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { VerifyEmailPage } from './pages/VerifyEmailPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { DashboardPage } from './pages/DashboardPage';
import { CertificateDetailPage } from './pages/CertificateDetailPage';

// Placeholder Components
const Placeholder = ({ title }: { title: string }) => (
  <div style={{ textAlign: 'center', padding: 'var(--spacing-12)' }}>
    <h2 style={{ color: 'var(--color-primary-700)', marginBottom: 'var(--spacing-4)' }}>{title}</h2>
    <p style={{ color: 'var(--color-neutral-700)' }}>Coming soon</p>
  </div>
);

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          {/* Public Routes */}
          <Route element={<PublicLayout />}>
            <Route path="/" element={<Navigate to="/verify" replace />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            
            <Route path="/verify" element={<VerificationPage />} />
            <Route path="/verify/:certId" element={<VerificationPage />} />
          </Route>

          {/* Authenticated Routes */}
          <Route element={<ProtectedRoute />}>
            <Route element={<AuthLayout />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/certificates/new" element={<Placeholder title="Issue Certificate" />} />
              <Route path="/certificates/:id" element={<CertificateDetailPage />} />
            </Route>
          </Route>
          
          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
