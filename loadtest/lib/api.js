// What every action needs to call Kith as a signed-in Load Test User.

import http from 'k6/http';
import { Rate } from 'k6/metrics';

export const SESSION_COOKIE = 'kith_session';

// One sample per action run: false when every request and check passed.
export const errors = new Rate('errors');

export function baseUrl(env) {
  const url = env.BASE_URL;
  if (!url) throw new Error('BASE_URL is not set, e.g. https://localhost');
  return url.replace(/\/+$/, '');
}

// Puts the Session in this VU's cookie jar, so page loads and their
// redirects carry it like a browser's would.
export function signIn(base, user) {
  http.cookieJar().set(base, SESSION_COOKIE, user.session_id, { secure: true, path: '/' });
}

// Headers of an API call from the app. Origin is what a browser sends; the
// API's Origin check reads it on state-changing requests.
export function apiHeaders(base, user, extra = {}) {
  return { 'X-Tenant-ID': user.tenant_id, Origin: base, ...extra };
}

export function json(response) {
  try {
    return response.json();
  } catch {
    return null;
  }
}
