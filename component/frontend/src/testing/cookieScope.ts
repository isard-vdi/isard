import Cookie from 'universal-cookie'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { effectScope, type EffectScope } from 'vue'
import { afterEach, beforeEach, expect } from 'vitest'
import { useCookies } from '@/lib/auth'

interface Polling {
  _startPolling(): void
  _stopPolling(): void
}

const proto = Cookie.prototype as unknown as Polling
const { _startPolling: startPolling, _stopPolling: stopPolling } = proto
const polling = new Set<Polling>()
proto._startPolling = function (this: Polling) {
  polling.add(this)
  startPolling.call(this)
}
proto._stopPolling = function (this: Polling) {
  polling.delete(this)
  stopPolling.call(this)
}

let scope: EffectScope
const pinias: Pinia[] = []

// A cookie poll left running fires after vitest tears jsdom down and fails the job.
export const stopCookiePollingAfterEach = () => {
  beforeEach(() => {
    scope = effectScope()
  })
  afterEach(() => {
    scope.stop()
    pinias.splice(0).forEach(disposePinia)
    expect(polling.size).toBe(0)
  })
}

export const scopedCookies = () => scope.run(useCookies) as ReturnType<typeof useCookies>

export const freshPinia = () => {
  const pinia = createPinia()
  pinias.push(pinia)
  setActivePinia(pinia)
}
