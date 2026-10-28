import { check } from 'k6';
import http from 'k6/http';

import { apiHeaders, json } from '../lib/api.js';
import { pick } from '../lib/queries.js';

// The Document list, then opening one: the preview asks for the PDF's
// presigned link. The PDF itself comes from S3, not Kith, so it isn't fetched.
// An empty list fails: opening a Document is half of what browse measures.
export function browse(base, user) {
  const list = http.get(`${base}/api/v1/documents`, {
    headers: apiHeaders(base, user),
    tags: { name: 'GET /api/v1/documents' },
  });
  const listed = check(list, {
    'browse: list 200': (r) => r.status === 200,
    'browse: has a Document': (r) => Array.isArray(json(r)) && json(r).length > 0,
  });
  if (!listed) return false;
  const documents = json(list);

  const opened = http.get(`${base}/api/v1/documents/${pick(documents).id}/file-url`, {
    headers: apiHeaders(base, user),
    tags: { name: 'GET /api/v1/documents/{id}/file-url' },
  });
  return check(opened, {
    'browse: file-url 200': (r) => r.status === 200,
    'browse: has a url': (r) => typeof json(r)?.url === 'string',
  });
}
