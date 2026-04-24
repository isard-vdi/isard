import type { Composer } from 'vue-i18n'
import type { ErrorResponse } from '@/gen/oas/apiv4'

type I18nLike = Pick<Composer, 't' | 'te'>

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
