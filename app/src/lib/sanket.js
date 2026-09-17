// Every SANKET call this app makes, in one file, written from contracts/openapi.json.
//
// Each function's doc comment names the operationId and its `x-roles`, and the keys a
// caller may rely on come from the contract's `x-response-shapes` block — which BE-7 added
// precisely so the two frontend lanes stop guessing at an open `data` payload. If a key is
// not listed there, no screen here depends on it.

import { apiFetch, apiData } from './api'

/** Drop empty values so an unset filter is an absent parameter, not `?product=`. */
function qs(params = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

// --------------------------------------------------------------------------- //
// queue + lead
// --------------------------------------------------------------------------- //

/**
 * `sanketQueue` — GET /sanket/queue — x-roles A, M, RM.
 * An RM is scoped to their own EIN below the role check; a manager sees everything.
 * @returns {Promise<{data: object[], meta: object}>} meta: total, limit, offset, scope,
 *   include_suppressed, model_run_id
 */
export function getQueue({
  product, tier, status, windowDue, rm, includeSuppressed, sort, limit, offset, signal,
} = {}) {
  return apiFetch(`/sanket/queue${qs({
    product,
    tier,
    status,
    window_due: windowDue,
    rm,
    include_suppressed: includeSuppressed ? 'true' : undefined,
    sort,
    limit,
    offset,
  })}`, { signal })
}

/** `sanketLead` — GET /sanket/lead/{id} — x-roles A, M, RM. */
export function getLead(leadId, { signal } = {}) {
  return apiData(`/sanket/lead/${encodeURIComponent(leadId)}`, { signal })
}

/**
 * `sanketDisposition` — POST /sanket/lead/{id}/disposition — x-roles A, M, RM.
 * Append-only: this records what happened on a call, it never edits a score.
 * @param {{outcome: string, product?: string, note?: string, callback_at?: string}} body
 */
export function postDisposition(leadId, body) {
  return apiData(`/sanket/lead/${encodeURIComponent(leadId)}/disposition`, { method: 'POST', body })
}

// --------------------------------------------------------------------------- //
// manager actions
// --------------------------------------------------------------------------- //

/**
 * `sanketAssign` — POST /sanket/assign — x-roles M, A.
 * Round-robin honours each RM's current load; the roster comes from the seeded users.
 * @param {{mode: 'round_robin'|'explicit'|'rebalance', lead_ids?: string[], rm_ein?: string}} body
 */
export function postAssign(body) {
  return apiData('/sanket/assign', { method: 'POST', body })
}

/**
 * `sanketCrmPush` — POST /sanket/lead/{id}/crm-push — x-roles M, A.
 *
 * The only write this platform makes into a bank system, so the contract makes it take
 * TWO deliberate flags: `dry_run: false` AND `confirm: true`. A client that forgets a
 * default cannot write by omission — a missing `confirm` is a 400. This wrapper keeps
 * that shape rather than hiding it behind a boolean, because the UI has to show the
 * difference to the person clicking.
 */
export function crmPushDryRun(leadId, { product, note } = {}) {
  return apiData(`/sanket/lead/${encodeURIComponent(leadId)}/crm-push`, {
    method: 'POST',
    body: { dry_run: true, product, note },
  })
}

export function crmPushConfirm(leadId, { product, note } = {}) {
  return apiData(`/sanket/lead/${encodeURIComponent(leadId)}/crm-push`, {
    method: 'POST',
    body: { dry_run: false, confirm: true, product, note },
  })
}

/** `sanketFunnel` — GET /sanket/funnel — x-roles M, A. The manager dashboard's one call. */
export function getFunnel({ signal } = {}) {
  return apiFetch('/sanket/funnel', { signal })
}

/**
 * `sanketValidation` — GET /sanket/validation — x-roles M, A, same as `getFunnel`.
 * The pre-registered report plus, when the model run recorded one, the accepted-failure
 * overlay: which failing criteria were named in advance and why.
 */
export function getValidation({ signal } = {}) {
  return apiFetch('/sanket/validation', { signal })
}

// --------------------------------------------------------------------------- //
// consent / Account Aggregator
// --------------------------------------------------------------------------- //

/** `consentList` — GET /sanket/consent/list — x-roles A, M, RM. */
export function getConsents({ custId, status, limit, offset, signal } = {}) {
  return apiFetch(`/sanket/consent/list${qs({ cust_id: custId, status, limit, offset })}`, { signal })
}

/** `consentGet` — GET /sanket/consent/{consent_id} — x-roles A, M, RM. */
export function getConsent(consentId, { signal } = {}) {
  return apiData(`/sanket/consent/${encodeURIComponent(consentId)}`, { signal })
}

/** `consentRequest` — POST /sanket/consent/request — x-roles A, M, RM. 201. */
export function postConsentRequest({ custId, purpose, fiTypes }) {
  return apiData('/sanket/consent/request', {
    method: 'POST',
    body: { cust_id: custId, purpose, fi_types: fiTypes },
  })
}

/** `consentFetch` — POST /sanket/consent/{id}/fetch — x-roles A, M, RM. 202, or 409 unless ACTIVE. */
export function postConsentFetch(consentId) {
  return apiData(`/sanket/consent/${encodeURIComponent(consentId)}/fetch`, { method: 'POST' })
}

/**
 * `consentReplay` — POST /sanket/consent/{id}/replay — x-roles A (admin only).
 * Re-injects a stored 497/498 delivery through the same state machine, for the case the
 * IDBI sandbox cannot reach a box with no public address. It is NOT the webhook with its
 * signature check removed: it is authenticated, admin-only, and audited under its own
 * action name, so nothing in the trail can be mistaken for a real delivery.
 */
export function postConsentReplay(consentId, { event, apiId } = {}) {
  return apiData(`/sanket/consent/${encodeURIComponent(consentId)}/replay`, {
    method: 'POST',
    body: { event, api_id: apiId },
  })
}

/** The AA states the database can actually store (migration 0001's check constraint). */
export const CONSENT_STATES = ['REQUESTED', 'PENDING', 'ACTIVE', 'REJECTED', 'REVOKED', 'EXPIRED', 'FAILED']

/** The webhook event names `replay` accepts, grouped by the state each drives. */
export const REPLAY_EVENTS = [
  { value: 'PENDING', label: 'PENDING — customer opened the AA app' },
  { value: 'ACTIVE', label: 'ACTIVE — customer approved' },
  { value: 'DATA_READY', label: 'DATA_READY — statements are fetchable' },
  { value: 'REJECTED', label: 'REJECTED — customer declined' },
  { value: 'REVOKED', label: 'REVOKED — customer withdrew consent' },
  { value: 'EXPIRED', label: 'EXPIRED — validity lapsed' },
  { value: 'FAILED', label: 'FAILED — the AA could not complete it' },
]

// --------------------------------------------------------------------------- //
// meta + admin
// --------------------------------------------------------------------------- //

/** `metaSync` — GET /meta/sync — any signed-in user. */
export function getSync({ signal } = {}) {
  return apiFetch('/meta/sync', { signal })
}

/** `metaProvenance` — GET /meta/provenance — any signed-in user. */
export function getProvenance({ signal } = {}) {
  return apiData('/meta/provenance', { signal })
}

/** `version` — GET /meta/version — unauthenticated. */
export function getVersion({ signal } = {}) {
  return apiData('/meta/version', { signal })
}

/** `adminUsersList` — GET /admin/users — x-roles A. */
export function getUsers({ signal } = {}) {
  return apiFetch('/admin/users', { signal })
}

/** `adminAudit` — GET /admin/audit — x-roles A. */
export function getAudit({ limit, offset, action, signal } = {}) {
  return apiFetch(`/admin/audit${qs({ limit, offset, action })}`, { signal })
}

/** `adminAuditVerify` — POST /admin/audit/verify — x-roles A. Walks the hash chain. */
export function verifyAudit() {
  return apiData('/admin/audit/verify', { method: 'POST' })
}

/** `adminBatchRun` — POST /admin/batch/run — x-roles A. Still 501 (BE-8's lane). */
export function runBatch(body) {
  return apiData('/admin/batch/run', { method: 'POST', body })
}
