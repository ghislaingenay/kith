import { check } from 'k6';
import { Trend } from 'k6/metrics';
import sse from 'k6/x/sse';

import { apiHeaders, SESSION_COOKIE } from '../lib/api.js';
import { ASK_QUERIES, pick } from '../lib/queries.js';

// From sending the Query to the first non-blank `answer_delta`, and to `done`.
const timeToFirstWord = new Trend('ask_time_to_first_word', true);
const duration = new Trend('ask_duration', true);

export function ask(base, user) {
  let firstWordAt = null;
  let doneAt = null;
  let streamFailed = false;
  const started = Date.now();
  const response = sse.open(
    `${base}/api/v1/asks`,
    {
      method: 'POST',
      body: JSON.stringify({ query: pick(ASK_QUERIES) }),
      headers: apiHeaders(base, user, {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        Cookie: `${SESSION_COOKIE}=${user.session_id}`,
      }),
      tags: { name: 'POST /api/v1/asks' },
      timeout: '60s',
    },
    (client) => {
      client.on('event', (event) => {
        if (event.name === 'answer_delta' && firstWordAt === null) {
          if (JSON.parse(event.data).text.trim()) firstWordAt = Date.now();
        } else if (event.name === 'done') {
          doneAt = Date.now();
          client.close();
        }
      });
      client.on('error', () => {
        streamFailed = true;
      });
    },
  );

  if (firstWordAt !== null) timeToFirstWord.add(firstWordAt - started);
  if (doneAt !== null) duration.add(doneAt - started);
  return check(response, {
    'ask: 200': (r) => r && r.status === 200,
    'ask: streamed a word': () => firstWordAt !== null,
    'ask: ended with done': () => doneAt !== null && !streamFailed,
  });
}
