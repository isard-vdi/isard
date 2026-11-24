import { describe, expect, it } from 'vitest'

import { hostToUnicode } from './hostName'

describe('hostToUnicode', () => {
  it('decodes an idna ascii host name', () => {
    expect(hostToUnicode('xn--ctedra-ita.cat')).toBe('càtedra.cat')
  })

  it('decodes the host inside a url', () => {
    expect(hostToUnicode('https://d1.xn--basti-4ta.acme.org:8443')).toBe(
      'https://d1.bastió.acme.org:8443'
    )
  })

  it('leaves an ascii host name as it is', () => {
    expect(hostToUnicode('acme.org')).toBe('acme.org')
  })

  it('leaves a label it cannot decode as it is', () => {
    expect(hostToUnicode('xn--ü.acme.org')).toBe('xn--ü.acme.org')
  })
})
