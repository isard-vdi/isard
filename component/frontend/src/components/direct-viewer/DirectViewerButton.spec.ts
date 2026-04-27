import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

const mutateMock = vi.fn()
const setCookieMock = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useMutation: () => ({ mutate: mutateMock, isPending: ref(false) })
}))

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  logViewerClickMutation: () => ({})
}))

vi.mock('jwt-decode', () => ({
  jwtDecode: (token: string) => {
    if (token === 'rdp-jwt') return { web_viewer: { exp: 1800000000 } }
    throw new Error(`unexpected jwt: ${token}`)
  }
}))

vi.mock('@vueuse/integrations/useCookies', () => ({
  useCookies: () => ({ set: setCookieMock })
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k })
}))

vi.mock('@/assets/img/viewers/vnc-browser.svg?component', () => ({
  default: { template: '<span data-test="browser-icon" />' }
}))
vi.mock('@/assets/img/viewers/spice.svg?component', () => ({
  default: { template: '<span data-test="file-icon" />' }
}))

vi.mock('@/components/ui/button', () => ({
  Button: {
    props: ['disabled'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
  }
}))
vi.mock('@/components/ui/spinner', () => ({
  Spinner: { template: '<span data-test="spinner" />' }
}))
vi.mock('@/components/ui/tooltip', () => ({
  Tooltip: { template: '<div><slot /></div>' },
  TooltipContent: { template: '<div><slot /></div>' },
  TooltipProvider: { template: '<div><slot /></div>' },
  TooltipTrigger: { template: '<div><slot /></div>' }
}))
vi.mock('@/components/icon', () => ({
  Icon: { template: '<span data-test="icon" />' }
}))

import DirectViewerButton from './DirectViewerButton.vue'

const factory = (overrides: Record<string, unknown> = {}) =>
  mount(DirectViewerButton, {
    props: {
      viewer: { kind: 'browser', protocol: 'vnc' },
      state: 'Started',
      token: 'tok',
      ...overrides
    }
  })

describe('DirectViewerButton', () => {
  beforeEach(() => {
    mutateMock.mockReset()
    setCookieMock.mockReset()
  })

  afterEach(() => {
    document.body.replaceChildren()
  })

  it('renders the localized button label for the kind/protocol pair', () => {
    const wrapper = factory({ viewer: { kind: 'browser', protocol: 'vnc' } })
    expect(wrapper.find('button').text()).toBe('viewers.browser-vnc')
  })

  it('disables the button and shows the waiting block when WAITING_IP and protocol needs IP', () => {
    const wrapper = factory({
      viewer: { kind: 'browser', protocol: 'rdp' },
      state: 'WaitingIP'
    })
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('views.direct-viewer.waitingip')
  })

  it('does not disable when WAITING_IP but protocol does not require IP (browser-vnc)', () => {
    const wrapper = factory({
      viewer: { kind: 'browser', protocol: 'vnc' },
      state: 'WaitingIP'
    })
    expect(wrapper.find('button').attributes('disabled')).toBeUndefined()
  })

  it('renders the help trigger only for spice/rdpgw protocols', async () => {
    const spice = factory({ viewer: { kind: 'file', protocol: 'spice' } })
    expect(spice.find('button[aria-label]').exists()).toBe(true)

    const vnc = factory({ viewer: { kind: 'browser', protocol: 'vnc' } })
    expect(vnc.find('button[aria-label]').exists()).toBe(false)
  })

  it('emits help with the protocol when the help trigger is clicked', async () => {
    const wrapper = factory({ viewer: { kind: 'file', protocol: 'spice' } })
    await wrapper.find('button[aria-label]').trigger('click')
    expect(wrapper.emitted('help')).toEqual([['spice']])
  })

  it('renders the description text when provided', () => {
    const wrapper = factory({ description: 'desc-text' })
    expect(wrapper.text()).toContain('desc-text')
  })

  describe('openViewer', () => {
    it('logs the click via mutation when activated', async () => {
      const wrapper = factory({
        viewer: {
          kind: 'browser',
          protocol: 'vnc',
          viewer: 'https://vw.example/path',
          cookie: encodeURIComponent(btoa(JSON.stringify({ web_viewer: { exp: 1800000000 } })))
        }
      })
      await wrapper.find('button:not([aria-label])').trigger('click')
      expect(mutateMock).toHaveBeenCalledWith({
        path: { token: 'tok', protocol: 'browser-vnc' }
      })
    })

    it('builds a data: URL and triggers a download for kind=file', async () => {
      const clickSpy = vi.fn()
      const origCreate = document.createElement.bind(document)
      vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        const el = origCreate(tag)
        if (tag === 'a') el.click = clickSpy
        return el
      })

      const wrapper = factory({
        viewer: {
          kind: 'file',
          protocol: 'spice',
          content: '[virt-viewer]\nx=1',
          mime: 'application/x-virt-viewer',
          name: 'connection',
          ext: 'vv'
        }
      })
      await wrapper.find('button:not([aria-label])').trigger('click')

      expect(clickSpy).toHaveBeenCalledTimes(1)
    })

    it('decodes RDP cookie via jwtDecode and writes browser_viewer cookie', async () => {
      const clickSpy = vi.fn()
      const origCreate = document.createElement.bind(document)
      vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        const el = origCreate(tag)
        if (tag === 'a') el.click = clickSpy
        return el
      })

      const wrapper = factory({
        viewer: {
          kind: 'browser',
          protocol: 'rdp',
          viewer: 'https://vw.example/rdp',
          cookie: 'rdp-jwt'
        }
      })
      await wrapper.find('button:not([aria-label])').trigger('click')

      expect(setCookieMock).toHaveBeenCalledTimes(1)
      const call = setCookieMock.mock.calls[0]
      expect(call[0]).toBe('browser_viewer')
      expect(call[1]).toBe('rdp-jwt')
      expect(call[2].path).toBe('/')
      expect(call[2].sameSite).toBe('strict')
      expect(call[2].expires).toBeInstanceOf(Date)
      expect(clickSpy).toHaveBeenCalled()
    })

    it('decodes VNC cookie via atob/JSON for non-rdp browser protocols', async () => {
      const clickSpy = vi.fn()
      const origCreate = document.createElement.bind(document)
      vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        const el = origCreate(tag)
        if (tag === 'a') el.click = clickSpy
        return el
      })

      const cookiePayload = encodeURIComponent(
        btoa(JSON.stringify({ web_viewer: { exp: 1800000000 } }))
      )
      const wrapper = factory({
        viewer: {
          kind: 'browser',
          protocol: 'vnc',
          viewer: 'https://vw.example/vnc',
          cookie: cookiePayload
        }
      })
      await wrapper.find('button:not([aria-label])').trigger('click')

      expect(setCookieMock).toHaveBeenCalledTimes(1)
      expect(setCookieMock.mock.calls[0][0]).toBe('browser_viewer')
      expect(clickSpy).toHaveBeenCalled()
    })

    it('appends ?direct=1 to the browser viewer URL', async () => {
      let captured: string | null = null
      const origCreate = document.createElement.bind(document)
      vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        const el = origCreate(tag)
        if (tag === 'a') {
          el.click = vi.fn()
          const realSet = el.setAttribute.bind(el)
          el.setAttribute = (name: string, value: string) => {
            if (name === 'href') captured = value
            realSet(name, value)
          }
        }
        return el
      })

      const cookiePayload = encodeURIComponent(
        btoa(JSON.stringify({ web_viewer: { exp: 1800000000 } }))
      )
      const wrapper = factory({
        viewer: {
          kind: 'browser',
          protocol: 'vnc',
          viewer: 'https://vw.example/vnc?token=abc',
          cookie: cookiePayload
        }
      })
      await wrapper.find('button:not([aria-label])').trigger('click')

      expect(captured).not.toBeNull()
      expect(captured).toContain('direct=1')
      expect(captured).toContain('token=abc')
    })

    it('returns silently when required fields are missing', async () => {
      const clickSpy = vi.fn()
      const origCreate = document.createElement.bind(document)
      vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        const el = origCreate(tag)
        if (tag === 'a') el.click = clickSpy
        return el
      })

      const wrapper = factory({ viewer: { kind: 'browser', protocol: 'rdpgw' } })
      await wrapper.find('button:not([aria-label])').trigger('click')

      expect(clickSpy).not.toHaveBeenCalled()
      expect(setCookieMock).not.toHaveBeenCalled()
    })
  })
})
