import type { Composer } from 'vue-i18n'
import type { ErrorResponse } from '@/gen/oas/apiv4'

type I18nLike = Pick<Composer, 't' | 'te'>

/**
 * Extracts the `description_code`(s) from an apiv4 error thrown by the OAS
 * client. The client throws the parsed `ErrorResponse` body directly (see the
 * `lib/faro-api.ts` error interceptor), in one of two shapes:
 *   - single error: `{ description_code, error, msg, ... }`
 *   - multi error:  `{ errors: [{ description_code, ... }, ...] }`
 * Returns one code per logical error, or `[]` when none can be determined.
 */
export function apiErrorCodes(err: unknown): string[] {
  const r = err as
    | (Partial<ErrorResponse> & { errors?: { description_code?: string }[] })
    | undefined
  if (Array.isArray(r?.errors)) {
    return r.errors.map((e) => e?.description_code).filter((c): c is string => !!c)
  }
  return r?.description_code ? [r.description_code] : []
}

/**
 * Maps each error code in an apiv4 error to a localized string under
 * `api.<domain>.errors.<code>`, falling back to `…errors.unknown` per code.
 * Handles both the single- and multi-error response shapes via
 * {@link apiErrorCodes}, so callers never parse the raw payload themselves.
 */
export function describeApiErrors(err: unknown, i18n: I18nLike, domain: string): string[] {
  const base = `api.${domain}.errors.`
  const codes = apiErrorCodes(err)
  const fallback = `${base}unknown`
  return (codes.length ? codes : ['unknown']).map((code) =>
    i18n.te(`${base}${code}`) ? i18n.t(`${base}${code}`) : i18n.t(fallback)
  )
}

/**
 * Maps an apiv4 error thrown by the OAS client to a localized string.
 *
 * Tries `api.<domain>.errors.<description_code>` first, then the top-level
 * HTTP class (e.g. `conflict`, `not_found`), then the raw `msg`, then a
 * generic fallback.
 */
export function describeApiError(err: unknown, i18n: I18nLike, domain: string): string {
  const r = err as Partial<ErrorResponse> | undefined

  for (const code of [r?.description_code, r?.error]) {
    if (!code) continue
    const key = `api.${domain}.errors.${code}`
    if (i18n.te(key)) return i18n.t(key)
  }

  return r?.msg || i18n.t(`api.${domain}.errors.generic`)
}

// Creating a desktop also runs the start quota checks (a temporal desktop is
// started right away), so the wizards receive start codes too. Each resource
// shares one message across its user/group/category variants.
const NEW_DESKTOP_ERROR_ALIASES: Record<string, string> = {
  desktop_start_user_quota_exceeded: 'desktop_start_quota_exceeded',
  desktop_start_group_limit_exceeded: 'desktop_start_quota_exceeded',
  desktop_start_category_limit_exceeded: 'desktop_start_quota_exceeded',
  desktop_start_memory_quota_exceeded: 'desktop_start_memory_quota_exceeded',
  desktop_start_group_memory_limit_exceeded: 'desktop_start_memory_quota_exceeded',
  desktop_start_category_memory_limit_exceeded: 'desktop_start_memory_quota_exceeded',
  desktop_start_vcpu_quota_exceeded: 'desktop_start_vcpu_quota_exceeded',
  desktop_start_group_vcpu_limit_exceeded: 'desktop_start_vcpu_quota_exceeded',
  desktop_start_category_vcpu_limit_exceeded: 'desktop_start_vcpu_quota_exceeded',
  total_size_quota_exceeded: 'desktop_start_disk_quota_exceeded',
  group_total_size_limit_exceeded: 'desktop_start_disk_quota_exceeded',
  category_total_size_limit_exceeded: 'desktop_start_disk_quota_exceeded'
}

/**
 * Resolves a desktop creation `description_code` to a key under
 * `api.new-desktop.errors.<key>` holding a `title` / `description` pair.
 * Falls back to `generic` when the code has no string in the active locale:
 * a generic message the user reads beats an English one they may not.
 */
export function newDesktopErrorKey(code: string | null, i18n: I18nLike): string {
  if (!code) return 'generic'
  const key = NEW_DESKTOP_ERROR_ALIASES[code] ?? code
  return i18n.te(`api.new-desktop.errors.${key}.title`) ? key : 'generic'
}
