import { describe, expect, it } from 'vitest'
import { TokenType, isRegisterClaims, isReRegisterClaims, parseToken } from './auth'

const buildJwt = (payload: object): string => {
  const encode = (o: object) =>
    btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_')

  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.signature`
}

describe('parseToken', () => {
  it('parses a re-register token as ReRegisterClaims', () => {
    const claims = parseToken(
      buildJwt({ type: 're-register', provider: 'saml', category_id: 'default' })
    )

    expect(claims.type).toBe(TokenType.ReRegister)
    expect(isReRegisterClaims(claims)).toBe(true)
    expect(isRegisterClaims(claims)).toBe(false)
  })

  it('keeps register tokens as RegisterClaims', () => {
    const claims = parseToken(
      buildJwt({ type: 'register', provider: 'saml', category_id: 'default' })
    )

    expect(isRegisterClaims(claims)).toBe(true)
    expect(isReRegisterClaims(claims)).toBe(false)
  })
})
