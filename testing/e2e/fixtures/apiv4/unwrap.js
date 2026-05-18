// Generic SDK-result unwrapping — no domain knowledge.

/**
 * Throw on SDK error payloads; return typed `data` otherwise.
 *
 * @template T
 * @param {Promise<{data?: T, error?: unknown, response: Response}>} promise
 * @returns {Promise<T>}
 */
export async function unwrap(promise) {
  const result = await promise
  if (result.error !== undefined && result.data === undefined) {
    const status = result.response?.status
    const detail = typeof result.error === 'string' ? result.error : JSON.stringify(result.error)
    const err = new Error(`apiv4 error ${status}: ${detail}`)
    err.status = status
    err.payload = result.error
    throw err
  }
  return result.data
}
