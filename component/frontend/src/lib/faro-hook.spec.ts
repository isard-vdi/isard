import { describe, expect, it } from 'vitest'
import { pageIdFor } from './faro-hook'

describe('pageIdFor', () => {
  it('keeps static paths untouched', () => {
    expect(pageIdFor('/desktops')).toBe('/desktops')
    expect(pageIdFor('/deployments/new')).toBe('/deployments/new')
  })

  it('replaces UUID segments', () => {
    expect(pageIdFor('/desktops/2f8a1c3e-1111-2222-3333-444455556666')).toBe('/desktops/{id}')
  })

  it('replaces long hex segments', () => {
    expect(pageIdFor('/media/9f86d081884c7d65')).toBe('/media/{id}')
  })

  it('replaces numeric segments', () => {
    expect(pageIdFor('/deployments/12345')).toBe('/deployments/{id}')
  })

  it('replaces segments longer than 32 characters', () => {
    expect(pageIdFor(`/a/${'x'.repeat(33)}`)).toBe('/a/{id}')
  })

  it('normalises the root', () => {
    expect(pageIdFor('/')).toBe('/')
    expect(pageIdFor('')).toBe('/')
  })

  it('replaces every id in a multi-segment path', () => {
    expect(pageIdFor('/deployments/12345/desktops/2f8a1c3e-1111-2222-3333-444455556666')).toBe(
      '/deployments/{id}/desktops/{id}'
    )
  })
})
