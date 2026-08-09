import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Table } from '../components/ui/Table';
import { StatusPill } from '../components/ui/StatusPill';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { API_BASE_URL } from '../api/config';
import { Search, ChevronLeft, ChevronRight } from 'lucide-react';
import type { CertificateDetail } from '../api/types';

interface PaginatedResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: CertificateDetail[];
}

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [certificates, setCertificates] = useState<CertificateDetail[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Filters and Pagination
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);

  const fetchCertificates = async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams();
      query.set('page', page.toString());
      if (search) query.set('search', search);
      if (statusFilter) query.set('status', statusFilter);

      const res = await fetch(`${API_BASE_URL}/certificates/?${query.toString()}`);
      if (!res.ok) throw new Error('Failed to fetch certificates');
      
      const data = (await res.json()) as PaginatedResponse;
      setCertificates(data.results);
      setHasNext(!!data.next);
      setHasPrev(!!data.previous);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Debounced search effect
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1); // Reset page on new search
      fetchCertificates();
    }, 300);
    return () => clearTimeout(timer);
  }, [search, statusFilter]);

  // Page change effect
  useEffect(() => {
    fetchCertificates();
  }, [page]);

  return (
    <div className="dashboard-page">
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">Certificates</h1>
          <p className="dashboard-subtitle">Manage and track issued certificates</p>
        </div>
        <Button onClick={() => navigate('/certificates/new')}>Issue Certificate</Button>
      </div>

      <Card className="dashboard-controls">
        <div className="dashboard-search">
          <Search size={18} className="search-icon" />
          <Input 
            label="" 
            value={search} 
            onChange={(e) => setSearch(e.target.value)} 
            placeholder="Search by recipient or ID..." 
            className="search-input-field"
          />
        </div>
        <div className="dashboard-filter">
          <select 
            className="input-field status-select" 
            value={statusFilter} 
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="VALID">Valid</option>
            <option value="PENDING">Pending</option>
            <option value="EXPIRED">Expired</option>
            <option value="REVOKED">Revoked</option>
            <option value="FAILED">Failed</option>
          </select>
        </div>
      </Card>

      <Card className="dashboard-table-card">
        {loading && certificates.length === 0 ? (
          <div className="dashboard-loading">Loading certificates...</div>
        ) : (
          <>
            <Table headers={['Certificate ID', 'Recipient', 'Issue Date', 'Status']}>
              {certificates.map((cert) => (
                <tr 
                  key={cert.certificate_id} 
                  onClick={() => navigate(`/certificates/${cert.certificate_id}`)}
                  className="table-row-clickable"
                >
                  <td style={{ fontFamily: 'monospace' }}>{cert.certificate_id}</td>
                  <td>{cert.recipient_name}</td>
                  <td>{cert.issue_date}</td>
                  <td>
                    <StatusPill status={cert.status} />
                  </td>
                </tr>
              ))}
              {certificates.length === 0 && (
                <tr>
                  <td colSpan={4} className="table-empty">No certificates found.</td>
                </tr>
              )}
            </Table>
            
            <div className="dashboard-pagination">
              <Button 
                variant="outline" 
                disabled={!hasPrev} 
                onClick={() => setPage(p => p - 1)}
              >
                <ChevronLeft size={16} /> Previous
              </Button>
              <span className="pagination-info">Page {page}</span>
              <Button 
                variant="outline" 
                disabled={!hasNext} 
                onClick={() => setPage(p => p + 1)}
              >
                Next <ChevronRight size={16} />
              </Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
};
