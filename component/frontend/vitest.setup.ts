import { afterAll } from 'vitest'

// An interval a spec leaves running (universal-cookie polls document.cookie every 300 ms
// once a listener is added outside a component scope) fires after jsdom is torn down.
const intervals = new Set<ReturnType<typeof setInterval>>()
const nativeSetInterval = globalThis.setInterval
const setIntervalTracked = ((...args: Parameters<typeof setInterval>) => {
  const id = nativeSetInterval(...args)
  intervals.add(id)
  return id
}) as typeof setInterval
globalThis.setInterval = setIntervalTracked

afterAll(() => {
  intervals.forEach((id) => clearInterval(id))
  intervals.clear()
})
