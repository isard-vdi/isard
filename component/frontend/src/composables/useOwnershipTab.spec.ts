import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

import { useOwnershipTab } from './useOwnershipTab'

const mocks = vi.hoisted(() => ({
  query: {} as Record<string, unknown>,
  replace: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: mocks.query }),
  useRouter: () => ({ replace: mocks.replace })
}))

// The checks resolve on a microtask, so a couple of flushes is all it takes.
const settle = async () => {
  await nextTick()
  await nextTick()
  await nextTick()
}

beforeEach(() => {
  mocks.query = {}
  mocks.replace.mockClear()
})

describe('useOwnershipTab', () => {
  it('opens on the owned tab when the user owns something', async () => {
    const hasShared = vi.fn().mockResolvedValue(true)
    const { activeTab, isResolving } = useOwnershipTab({
      hasOwned: () => Promise.resolve(true),
      hasShared
    })

    expect(activeTab.value).toBeUndefined()
    expect(isResolving.value).toBe(true)

    await settle()

    expect(activeTab.value).toBe('user')
    expect(isResolving.value).toBe(false)
    // Nothing owned is the only reason to ask about shared items.
    expect(hasShared).not.toHaveBeenCalled()
  })

  it('opens on the shared tab when the user owns nothing but has shared items', async () => {
    const { activeTab } = useOwnershipTab({
      hasOwned: () => Promise.resolve(false),
      hasShared: () => Promise.resolve(true)
    })

    await settle()

    expect(activeTab.value).toBe('shared')
    // An autoselected tab is a per-visit decision, not something to pin in the URL.
    expect(mocks.replace).not.toHaveBeenCalled()
  })

  it('stays on the owned tab when there is nothing anywhere', async () => {
    const { activeTab } = useOwnershipTab({
      hasOwned: () => Promise.resolve(false),
      hasShared: () => Promise.resolve(false)
    })

    await settle()

    expect(activeTab.value).toBe('user')
  })

  it.each([
    ['owned', () => Promise.reject(new Error('boom')), () => Promise.resolve(true)],
    ['shared', () => Promise.resolve(false), () => Promise.reject(new Error('boom'))]
  ])('falls back to the owned tab when the %s check fails', async (_name, hasOwned, hasShared) => {
    const { activeTab, isResolving } = useOwnershipTab({ hasOwned, hasShared })

    await settle()

    expect(activeTab.value).toBe('user')
    expect(isResolving.value).toBe(false)
  })

  it('honours a tab pinned in the URL without running any check', async () => {
    mocks.query = { tab: 'shared' }
    const hasOwned = vi.fn().mockResolvedValue(true)
    const { activeTab, isResolving } = useOwnershipTab({
      hasOwned,
      hasShared: () => Promise.resolve(false)
    })

    expect(activeTab.value).toBe('shared')
    expect(isResolving.value).toBe(false)

    await settle()

    expect(hasOwned).not.toHaveBeenCalled()
  })

  it('ignores a query param that is not a tab', async () => {
    mocks.query = { tab: 'nonsense' }
    const { activeTab } = useOwnershipTab({
      hasOwned: () => Promise.resolve(false),
      hasShared: () => Promise.resolve(true)
    })

    await settle()

    expect(activeTab.value).toBe('shared')
  })

  it('keeps a tab picked while the checks are still in flight', async () => {
    const { activeTab, isResolving } = useOwnershipTab({
      hasOwned: () => Promise.resolve(false),
      hasShared: () => Promise.resolve(true)
    })

    activeTab.value = 'user'
    expect(isResolving.value).toBe(false)

    await settle()

    expect(activeTab.value).toBe('user')
  })

  it('skips every check when the caller hands it a settled tab', async () => {
    const hasOwned = vi.fn().mockResolvedValue(true)
    const { activeTab, isResolving } = useOwnershipTab({
      hasOwned,
      hasShared: () => Promise.resolve(false),
      pinned: 'shared'
    })

    expect(activeTab.value).toBe('shared')
    expect(isResolving.value).toBe(false)

    await settle()

    expect(hasOwned).not.toHaveBeenCalled()
  })

  it('takes the caller over the URL when both name a tab', async () => {
    mocks.query = { tab: 'user' }
    const { activeTab } = useOwnershipTab({
      hasOwned: () => Promise.resolve(true),
      hasShared: () => Promise.resolve(false),
      pinned: 'shared'
    })

    expect(activeTab.value).toBe('shared')
  })

  it('lands on the given fallback when there is nothing anywhere', async () => {
    const { activeTab } = useOwnershipTab({
      hasOwned: () => Promise.resolve(false),
      hasShared: () => Promise.resolve(false),
      fallback: () => 'shared'
    })

    await settle()

    expect(activeTab.value).toBe('shared')
  })

  it('leaves the URL alone when it is not the tab owner', async () => {
    mocks.query = { tab: 'shared' }
    const { activeTab, isResolving } = useOwnershipTab({
      hasOwned: () => Promise.resolve(true),
      hasShared: () => Promise.resolve(false),
      param: false
    })

    // The param is not read either: this list is not the page the URL describes.
    expect(activeTab.value).toBeUndefined()
    expect(isResolving.value).toBe(true)

    await settle()
    activeTab.value = 'shared'

    expect(mocks.replace).not.toHaveBeenCalled()
  })

  it('pins a hand-picked tab in the URL', async () => {
    mocks.query = { foo: 'bar' }
    const { activeTab } = useOwnershipTab({
      hasOwned: () => Promise.resolve(true),
      hasShared: () => Promise.resolve(false)
    })

    await settle()
    activeTab.value = 'shared'

    expect(activeTab.value).toBe('shared')
    expect(mocks.replace).toHaveBeenCalledWith({ query: { foo: 'bar', tab: 'shared' } })
  })
})
