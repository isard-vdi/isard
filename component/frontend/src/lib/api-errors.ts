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
