// Roles, in the two spellings the platform uses.
//
// contracts/openapi.json spells a principal's role in full (`credit_officer`) inside the
// session envelope, and in short codes (`CO`) in every route's `x-roles`. Guards accept
// either so a route can be written straight from the contract.

export const ROLE = {
  ADMIN: 'admin',
  MANAGER: 'manager',
  CREDIT_OFFICER: 'credit_officer',
  RELATIONSHIP_MANAGER: 'relationship_manager',
}

export const ROLE_CODE = {
  [ROLE.ADMIN]: 'A',
  [ROLE.MANAGER]: 'M',
  [ROLE.CREDIT_OFFICER]: 'CO',
  [ROLE.RELATIONSHIP_MANAGER]: 'RM',
}

export const CODE_ROLE = Object.fromEntries(Object.entries(ROLE_CODE).map(([role, code]) => [code, role]))

export const ROLE_LABEL = {
  [ROLE.ADMIN]: 'Administrator',
  [ROLE.MANAGER]: 'Manager',
  [ROLE.CREDIT_OFFICER]: 'Credit officer',
  [ROLE.RELATIONSHIP_MANAGER]: 'Relationship manager',
}

export const ALL_ROLES = Object.values(ROLE)

/** Accepts `credit_officer` or `CO` (any case) and returns the canonical role, or null. */
export function normaliseRole(value) {
  if (!value) return null
  const text = String(value).trim()
  if (ROLE_CODE[text.toLowerCase()]) return text.toLowerCase()
  const code = CODE_ROLE[text.toUpperCase()]
  return code || null
}

export const roleLabel = (value) => ROLE_LABEL[normaliseRole(value)] || 'Signed in'
export const roleCode = (value) => ROLE_CODE[normaliseRole(value)] || null

/**
 * Does `role` satisfy `allowed`?
 * An empty/absent `allowed` means "any signed-in user" — the contract's ["A","M","CO","RM"].
 */
export function roleMatches(role, allowed) {
  const actual = normaliseRole(role)
  if (!actual) return false
  const list = allowed == null ? [] : Array.isArray(allowed) ? allowed : [allowed]
  if (list.length === 0) return true
  return list.some((entry) => normaliseRole(entry) === actual)
}
