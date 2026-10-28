// The k6 options for a run mode, built from config.json alone, so a change
// to the traffic mix, think time or an SLO never touches an action module.

export const MODES = ['smoke', 'load', 'stress'];

// Action names are fixed: they tag every metric, and Grafana reads them too.
export const ACTIONS = ['search', 'ask', 'browse', 'upload', 'app_shell'];

// Smoke runs in CI, which has no AI keys.
const SKIPPED_IN_SMOKE = ['ask'];

export function enabledActions(mode) {
  return mode === 'smoke' ? ACTIONS.filter((a) => !SKIPPED_IN_SMOKE.includes(a)) : ACTIONS;
}

function positiveInt(name, value) {
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1) {
    throw new Error(`${name} must be a whole number of at least 1, got '${value}'`);
  }
  return n;
}

function scenario(mode, config, env) {
  if (mode === 'smoke') {
    // One pass over every action, in order: a weighted pick could miss one.
    return {
      executor: 'per-vu-iterations',
      vus: 1,
      iterations: enabledActions(mode).length,
      maxDuration: '5m',
    };
  }
  if (mode === 'load') {
    return {
      executor: 'constant-vus',
      vus: positiveInt('LOADTEST_VUS', env.LOADTEST_VUS),
      duration: config.load.duration,
    };
  }
  const maxVus = positiveInt('LOADTEST_STRESS_MAX_VUS', env.LOADTEST_STRESS_MAX_VUS);
  const { steps, step_duration } = config.stress;
  const stages = [];
  for (let step = 1; step <= steps; step++) {
    const target = Math.max(1, Math.round((maxVus * step) / steps));
    stages.push({ duration: '30s', target }, { duration: step_duration, target });
  }
  return { executor: 'ramping-vus', startVUs: 0, stages, gracefulRampDown: '30s' };
}

// The SLO limits a mode is judged by: Load passes or fails at the SLOs,
// Stress stops at the stop rule, smoke ignores latency (CI runners vary).
function limits(mode, config) {
  const { slos, stress_stop } = config;
  if (mode === 'load') {
    return {
      factor: 1,
      errorRate: slos.error_rate,
      abort: false,
    };
  }
  if (mode === 'stress') {
    return {
      factor: stress_stop.slo_multiplier,
      errorRate: stress_stop.error_rate,
      abort: true,
    };
  }
  return null;
}

function thresholds(mode, config) {
  const t = {};
  // A no-op threshold per action makes the end-of-test summary list its
  // p50/p95/p99 and error rate separately.
  for (const action of enabledActions(mode)) {
    if (action !== 'ask') t[`http_req_duration{action:${action}}`] = ['max>=0'];
    t[`errors{action:${action}}`] = ['rate>=0'];
  }
  if (mode === 'smoke') {
    t.errors = ['rate==0'];
    t.checks = ['rate==1'];
    return t;
  }

  t.ask_time_to_first_word = ['max>=0'];
  t.ask_duration = ['max>=0'];
  const { factor, errorRate, abort } = limits(mode, config);
  // Stress waits a minute before judging, so the first requests of a step
  // don't stop it on their own.
  const rule = (expression) =>
    abort ? { threshold: expression, abortOnFail: true, delayAbortEval: '1m' } : expression;
  const { slos } = config;
  t['http_req_duration{action:search}'].push(rule(`p(95)<=${slos.search_p95_ms * factor}`));
  t['http_req_duration{action:browse}'].push(rule(`p(95)<=${slos.browse_p95_ms * factor}`));
  t.ask_time_to_first_word.push(rule(`p(95)<=${slos.ask_first_word_p95_ms * factor}`));
  t.errors = [rule(`rate<=${errorRate}`)];
  return t;
}

export function buildOptions(mode, config, env) {
  if (!MODES.includes(mode)) {
    throw new Error(`MODE must be one of ${MODES.join(', ')}, got '${mode}'`);
  }
  const weights = config.traffic_mix;
  for (const action of ACTIONS) {
    if (!(weights[action] >= 0)) throw new Error(`traffic_mix.${action} is missing`);
  }
  return {
    scenarios: { [mode]: scenario(mode, config, env) },
    thresholds: thresholds(mode, config),
    summaryTrendStats: ['avg', 'p(50)', 'p(95)', 'p(99)', 'max'],
    // Presigned URLs and Document ids would each start a new time series.
    systemTags: ['status', 'method', 'name', 'group', 'check', 'error_code', 'scenario', 'expected_response'],
  };
}

// The action an iteration runs: each in turn for smoke, otherwise weighted
// by the traffic mix.
export function pickAction(mode, config, iteration) {
  const actions = enabledActions(mode);
  if (mode === 'smoke') return actions[iteration % actions.length];
  const weights = config.traffic_mix;
  const total = actions.reduce((sum, a) => sum + weights[a], 0);
  let roll = Math.random() * total;
  for (const action of actions) {
    roll -= weights[action];
    if (roll < 0) return action;
  }
  return actions[actions.length - 1];
}

export function thinkTimeSeconds(mode, config) {
  if (mode === 'smoke') return 0;
  const { min, max } = config.think_time_seconds;
  return min + Math.random() * (max - min);
}
