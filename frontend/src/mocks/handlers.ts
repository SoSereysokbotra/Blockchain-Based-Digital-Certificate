import { http, HttpResponse, delay } from 'msw';
import { mockCertificates, mockVerificationResults } from './fixtures';


// Simulate a realistic network delay for all handlers
const NETWORK_DELAY = 500;

export const handlers = [
  // --- AUTHENTICATION ENDPOINTS ---

  http.post('/api/auth/register/', async () => {
    await delay(NETWORK_DELAY);
    return HttpResponse.json({ message: 'Success' }, { status: 201 });
  }),

  http.post('/api/auth/verify-email/', async () => {
    await delay(NETWORK_DELAY);
    return HttpResponse.json({ message: 'Email verified' }, { status: 200 });
  }),

  http.post('/api/auth/login/', async ({ request }) => {
    await delay(NETWORK_DELAY);
    const body = await request.json() as any;
    if (body.email === 'locked@example.com') {
      return HttpResponse.json({ detail: 'Account locked. Try again later.' }, { status: 423 });
    }
    if (body.email === 'error@example.com') {
      return HttpResponse.json({ detail: 'Invalid credentials.' }, { status: 401 });
    }
    // Success scenario
    return HttpResponse.json({ access_token: 'mock_jwt_access_token' }, {
      headers: {
        'Set-Cookie': 'refresh_token=mock_jwt_refresh_token; HttpOnly; Path=/; Max-Age=604800;'
      }
    });
  }),

  http.post('/api/auth/refresh-token/', async () => {
    await delay(NETWORK_DELAY);
    return HttpResponse.json({ access_token: 'new_mock_jwt_access_token' });
  }),

  http.post('/api/auth/logout/', async () => {
    await delay(NETWORK_DELAY);
    return HttpResponse.json({ message: 'Logged out' }, {
      headers: {
        'Set-Cookie': 'refresh_token=; HttpOnly; Path=/; Max-Age=0;'
      }
    });
  }),

  http.post('/api/auth/request-password-reset/', async () => {
    await delay(NETWORK_DELAY);
    return HttpResponse.json({ message: 'Password reset requested' });
  }),

  http.post('/api/auth/verify-password-reset/', async () => {
    await delay(NETWORK_DELAY);
    return HttpResponse.json({ message: 'Code verified' });
  }),

  http.post('/api/auth/reset-password/', async () => {
    await delay(NETWORK_DELAY);
    return HttpResponse.json({ message: 'Password reset successfully' });
  }),

  // --- CERTIFICATE MANAGEMENT ENDPOINTS ---

  http.post('/api/certificates/', async () => {
    await delay(NETWORK_DELAY);
    return HttpResponse.json({
      certificate_id: `cert-new-${Date.now()}`,
      status: 'PENDING',
      pdf_url: 'https://example.com/certs/new.pdf'
    }, { status: 202 });
  }),

  http.get('/api/certificates/', async ({ request }) => {
    await delay(NETWORK_DELAY);
    const url = new URL(request.url);
    const page = Number(url.searchParams.get('page') || '1');
    const search = url.searchParams.get('search') || '';

    let filtered = mockCertificates;
    if (search) {
      const lowerSearch = search.toLowerCase();
      filtered = filtered.filter(cert => 
        cert.recipient_name.toLowerCase().includes(lowerSearch) || 
        cert.certificate_id.toLowerCase().includes(lowerSearch)
      );
    }

    const pageSize = 25;
    const startIndex = (page - 1) * pageSize;
    const paginated = filtered.slice(startIndex, startIndex + pageSize);

    return HttpResponse.json({
      count: filtered.length,
      next: startIndex + pageSize < filtered.length ? `/api/certificates/?page=${page + 1}` : null,
      previous: page > 1 ? `/api/certificates/?page=${page - 1}` : null,
      results: paginated.map(cert => ({
        certificate_id: cert.certificate_id,
        recipient_name: cert.recipient_name,
        issue_date: cert.issue_date,
        status: cert.status
      }))
    });
  }),

  http.get('/api/certificates/:id/', async ({ params }) => {
    await delay(NETWORK_DELAY);
    const cert = mockCertificates.find(c => c.certificate_id === params.id);
    if (!cert) {
      return HttpResponse.json({ detail: 'Not found.' }, { status: 404 });
    }
    return HttpResponse.json(cert);
  }),

  http.post('/api/certificates/:id/revoke/', async ({ params }) => {
    await delay(NETWORK_DELAY);
    const certIndex = mockCertificates.findIndex(c => c.certificate_id === params.id);
    if (certIndex === -1) {
      return HttpResponse.json({ detail: 'Not found.' }, { status: 404 });
    }
    // Update the mock state just for this session if needed, but for MSW fixtures usually a static response is fine
    // mockCertificates[certIndex].status = 'REVOKED';
    return HttpResponse.json({ message: 'Revocation started' }, { status: 202 });
  }),

  http.post('/api/certificates/:id/retry/', async () => {
    await delay(NETWORK_DELAY);
    return HttpResponse.json({ message: 'Retry started' }, { status: 202 });
  }),

  // --- PUBLIC ENDPOINTS ---

  http.get('/api/public/verify/:cert_id/', async ({ params }) => {
    await delay(NETWORK_DELAY);
    const result = mockVerificationResults[params.cert_id as string];
    if (!result) {
      return HttpResponse.json({
        status: 'NOT_FOUND',
      }, { status: 404 });
    }
    return HttpResponse.json(result);
  })
];
