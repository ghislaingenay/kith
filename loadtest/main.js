// Kith's load test (ADR-0021). Each iteration is one user action, picked by
// the traffic mix in config.json, then a pause to read.
//
//   MODE=smoke|load|stress BASE_URL=https://... SESSIONS_FILE=/abs/sessions.json \
//     ./k6 run loadtest/main.js

import { sleep } from 'k6';
import { SharedArray } from 'k6/data';
import exec from 'k6/execution';

import { appShell } from './actions/app_shell.js';
import { ask } from './actions/ask.js';
import { browse } from './actions/browse.js';
import { search } from './actions/search.js';
import { deleteDocument, upload, uploadDocument } from './actions/upload.js';
import { baseUrl, errors, signIn } from './lib/api.js';
import { buildOptions, pickAction, thinkTimeSeconds } from './lib/options.js';

const config = JSON.parse(open('./config.json'));
const mode = __ENV.MODE;
const base = baseUrl(__ENV);

// Written by `make load-test-sessions`. Never logged: a Session id is a
// live sign-in.
const users = new SharedArray('load test users', () => {
  if (!__ENV.SESSIONS_FILE) throw new Error('SESSIONS_FILE is not set');
  const rows = JSON.parse(open(__ENV.SESSIONS_FILE));
  if (rows.length === 0) throw new Error('SESSIONS_FILE has no Sessions');
  return rows.map(({ tenant_id, session_id }) => ({ tenant_id, session_id }));
});

const run = { search, ask, browse, upload, app_shell: appShell };

export const options = buildOptions(mode, config, __ENV);

// Smoke's Load Test Tenant starts empty, so browse gets one Document to open.
export function setup() {
  if (mode !== 'smoke') return {};
  signIn(base, users[0]);
  const id = uploadDocument(base, users[0]);
  if (id === null) throw new Error('smoke setup: the Document for browse did not upload');
  return { id };
}

export function teardown(data) {
  if (data.id) {
    signIn(base, users[0]);
    deleteDocument(base, users[0], data.id);
  }
}

export default function () {
  const user = users[(exec.vu.idInTest - 1) % users.length];
  signIn(base, user);

  const action = pickAction(mode, config, exec.vu.iterationInScenario);
  // Tags every metric this action emits, checks and errors included.
  exec.vu.metrics.tags.action = action;
  let ok = false;
  try {
    ok = run[action](base, user);
  } finally {
    // An action that throws counts as an error too.
    errors.add(!ok);
    delete exec.vu.metrics.tags.action;
  }
  sleep(thinkTimeSeconds(mode, config));
}
