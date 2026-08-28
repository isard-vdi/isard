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
  const base = `api.${domain}.errors`
  const codes = apiErrorCodes(err)
  return (codes.length ? codes : [null]).map((code) =>
    describeErrorCode(code, i18n, base, `${base}.unknown`)
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

/**
 * Localized message for an error `code` under `base`.
 *
 * Falls back to `fallbackKey` (`<base>.generic` by default) whenever the code
 * is absent or has no string in the *active* locale. Deliberately not `t`'s
 * default-message argument: that resolves through the fallback locale first,
 * showing English to users who may not read it, where a generic message in
 * their own language always lands.
 */
export function describeErrorCode(
  code: string | null | undefined,
  i18n: I18nLike,
  base: string,
  fallbackKey = `${base}.generic`
): string {
  const key = `${base}.${code}`
  return code && i18n.te(key) ? i18n.t(key) : i18n.t(fallbackKey)
}

/**
 * Same resolution as {@link describeErrorCode}, but for entries holding a
 * `title` / `description` pair: returns the key segment to interpolate, or
 * `generic`. `aliases` folds several codes onto one entry.
 */
export function errorCodeKey(
  code: string | null | undefined,
  i18n: I18nLike,
  base: string,
  aliases: Record<string, string> = {}
): string {
  if (!code) return 'generic'
  const key = aliases[code] ?? code
  return i18n.te(`${base}.${key}.title`) ? key : 'generic'
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

/** {@link errorCodeKey} for the desktop creation wizards, start codes folded in. */
export function newDesktopErrorKey(code: string | null | undefined, i18n: I18nLike): string {
  return errorCodeKey(code, i18n, 'api.new-desktop.errors', NEW_DESKTOP_ERROR_ALIASES)
}
