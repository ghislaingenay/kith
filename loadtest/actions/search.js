import { check } from 'k6';
import http from 'k6/http';

import { apiHeaders, json } from '../lib/api.js';
import { pick, SEARCH_QUERIES } from '../lib/queries.js';

export function search(base, user) {
  const response = http.post(
    `${base}/api/v1/search`,
    JSON.stringify({ query: pick(SEARCH_QUERIES) }),
    {
      headers: apiHeaders(base, user, { 'Content-Type': 'application/json' }),
      tags: { name: 'POST /api/v1/search' },
    },
  );
  return check(response, {
    'search: 200': (r) => r.status === 200,
    'search: has results': (r) => Array.isArray(json(r)?.results),
  });
}
