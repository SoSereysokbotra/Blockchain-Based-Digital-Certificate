import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
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
import { IssueCertificatePage } from './pages/IssueCertificatePage';

function App() {
  return (
    <AuthProvider>
      <ToastProvider>
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
                <Route path="/certificates/new" element={<IssueCertificatePage />} />
                <Route path="/certificates/:id" element={<CertificateDetailPage />} />
              </Route>
            </Route>
            
            {/* Catch-all */}
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </Router>
      </ToastProvider>
    </AuthProvider>
  );
}

export default App;
