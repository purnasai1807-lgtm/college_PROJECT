import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Safety default: localhost only. Never point this script at the production site.
const BASE_URL = (__ENV.BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const ALLOW_STAGING = (__ENV.K6_ALLOW_STAGING || '').toLowerCase() === 'true';
const PRODUCTION_HOSTS = new Set(['collegeproject-sandy.vercel.app']);
const parsedBase = new URL(BASE_URL);
const isLocal = ['localhost', '127.0.0.1', '::1'].includes(parsedBase.hostname);
const looksLikeStaging = /(^|[.-])(staging|stage|preprod|test)([.-]|$)/i.test(parsedBase.hostname);

if (PRODUCTION_HOSTS.has(parsedBase.hostname.toLowerCase()) || parsedBase.hostname.toLowerCase().endsWith('.vercel.app')) {
  throw new Error(`Safety stop: production/Vercel hosts are not permitted for load tests: ${parsedBase.hostname}`);
}
if (!isLocal && !(ALLOW_STAGING && looksLikeStaging)) {
  throw new Error('Safety stop: BASE_URL must be localhost. For a dedicated staging hostname containing staging/stage/preprod/test, set K6_ALLOW_STAGING=true explicitly.');
}

const workflowErrors = new Rate('workflow_errors');
const headers = { headers: { Accept: 'application/json,text/html,*/*' }, tags: { app: 'ace-canteen' } };

export const options = {
  stages: [
    { duration: '1m', target: 20 },
    { duration: '2m', target: 20 },
    { duration: '1m', target: 50 },
    { duration: '2m', target: 50 },
    { duration: '1m', target: 100 },
    { duration: '3m', target: 100 },
    { duration: '1m', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
    workflow_errors: ['rate<0.01'],
    'http_req_duration{endpoint:products}': ['p(95)<500'],
    'http_req_duration{endpoint:categories}': ['p(95)<500'],
    'http_req_duration{endpoint:canteen_status}': ['p(95)<500'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  userAgent: 'ACE-Canteen-k6-local-load-test/1.0',
};

function getAndCheck(path, endpoint, validate) {
  const response = http.get(`${BASE_URL}${path}`, {
    headers: headers.headers,
    tags: { app: 'ace-canteen', endpoint },
    timeout: '10s',
  });
  const passed = check(response, {
    [`${endpoint}: HTTP 200`]: (r) => r.status === 200,
    [`${endpoint}: response is not empty`]: (r) => !!r.body && r.body.length > 0,
    [`${endpoint}: payload shape is valid`]: validate,
  });
  workflowErrors.add(!passed);
  return response;
}

export default function () {
  // 1. Open the app's main page.
  getAndCheck('/', 'homepage', (r) => r.status === 200 && String(r.headers['Content-Type'] || '').includes('text/html'));
  sleep(1 + Math.random() * 2);

  // 2. Check database readiness (read-only SELECT 1).
  getAndCheck('/api/ready', 'readiness', (r) => {
    if (r.status !== 200) return false;
    try { return JSON.parse(r.body).status === 'ready'; } catch (_) { return false; }
  });
  sleep(1 + Math.random() * 2);

  // 3. Load active categories for the catalogue.
  getAndCheck('/api/categories', 'categories', (r) => {
    if (r.status !== 200) return false;
    try { return Array.isArray(JSON.parse(r.body)); } catch (_) { return false; }
  });
  sleep(1 + Math.random() * 2);

  // 4. Load the first page of in-stock products (same public endpoint as the UI).
  getAndCheck('/api/products?available_only=true&sort_by=name&sort_order=asc&limit=50&offset=0', 'products', (r) => {
    if (r.status !== 200) return false;
    try { return Array.isArray(JSON.parse(r.body)); } catch (_) { return false; }
  });
  sleep(1 + Math.random() * 2);

  // 5. Check current canteen/ordering status. No order or payment is created.
  getAndCheck('/api/canteen/status', 'canteen_status', (r) => {
    if (r.status !== 200) return false;
    try { return !!JSON.parse(r.body) && typeof JSON.parse(r.body) === 'object'; } catch (_) { return false; }
  });
  sleep(1 + Math.random() * 2);
}
