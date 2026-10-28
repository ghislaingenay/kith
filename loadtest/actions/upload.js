import crypto from 'k6/crypto';
import { check } from 'k6';
import http from 'k6/http';

import { apiHeaders, json } from '../lib/api.js';
import { onePagePdf } from '../lib/pdf.js';

const JSON_TYPE = { 'Content-Type': 'application/json' };

// The direct-to-S3 path (ADR-0009), then the Document is deleted, so the
// Tenant's free slots (5 of the 20-Document limit) never run out during a run.
export function upload(base, user) {
  const id = uploadDocument(base, user);
  if (id === null) return false;
  return deleteDocument(base, user, id);
}

// Init, PUT the file to the presigned URL, finalize. The new Document's id,
// or null when a step failed.
export function uploadDocument(base, user) {
  const pdf = onePagePdf(`Load test upload ${Date.now()} ${Math.random()}`);
  const init = http.post(
    `${base}/api/v1/uploads/init`,
    JSON.stringify({
      filename: 'load-test-upload.pdf',
      size: pdf.length,
      content_type: 'application/pdf',
      sha256: crypto.sha256(pdf, 'hex'),
    }),
    { headers: apiHeaders(base, user, JSON_TYPE), tags: { name: 'POST /api/v1/uploads/init' } },
  );
  const started = check(init, { 'upload: init 201': (r) => r.status === 201 });
  if (!started) return null;
  const { upload_id, url, headers } = json(init);

  const put = http.put(url, pdf, { headers, tags: { name: 'PUT presigned upload' } });
  if (!check(put, { 'upload: PUT 200': (r) => r.status === 200 })) return null;

  const finalize = http.post(`${base}/api/v1/uploads/${upload_id}/finalize`, null, {
    headers: apiHeaders(base, user),
    tags: { name: 'POST /api/v1/uploads/{id}/finalize' },
  });
  const finalized = check(finalize, {
    'upload: finalize 200': (r) => r.status === 200,
    'upload: is a Document': (r) => typeof json(r)?.id === 'string',
  });
  return finalized ? json(finalize).id : null;
}

export function deleteDocument(base, user, id) {
  const removed = http.del(`${base}/api/v1/documents/${id}`, null, {
    headers: apiHeaders(base, user),
    tags: { name: 'DELETE /api/v1/documents/{id}' },
  });
  return check(removed, { 'upload: delete 204': (r) => r.status === 204 });
}
