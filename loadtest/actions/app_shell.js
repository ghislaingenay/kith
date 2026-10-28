import { check } from 'k6';
import http from 'k6/http';

import { apiHeaders } from '../lib/api.js';

// Where `/` sends the browser. `app/loading.tsx` makes the page stream, so
// the status is sent before `redirect()` runs, and Next.js puts the redirect
// in a refresh meta tag instead of a 3xx that k6 would follow.
function landing(r) {
  const tag = (r.body || '').match(/<meta[^>]*id="__next-page-redirect"[^>]*>/);
  const target = tag && tag[0].match(/content="\d+;url=([^"]+)"/);
  return target ? target[1] : r.url;
}

// Opening Kith signed in: `/` redirects to the workspace, which the server
// renders from `/me`, then the shell loads the Credit Balance.
export function appShell(base, user) {
  const page = http.get(`${base}/`, { tags: { name: 'GET /' } });
  const balance = http.get(`${base}/api/v1/credit-balance`, {
    headers: apiHeaders(base, user),
    tags: { name: 'GET /api/v1/credit-balance' },
  });
  const pageOk = check(page, {
    'app_shell: page 200': (r) => r.status === 200,
    'app_shell: lands in the workspace': (r) => landing(r).includes('/w/'),
  });
  const balanceOk = check(balance, {
    'app_shell: credit-balance 200': (r) => r.status === 200,
  });
  return pageOk && balanceOk;
}
