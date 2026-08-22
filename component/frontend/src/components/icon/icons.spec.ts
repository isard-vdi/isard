import { describe, expect, it } from 'vitest'

import { getIcon } from './icons'

describe('getIcon', () => {
  it('hands every instance of a name the same component definition', () => {
    expect(getIcon('play')).toBe(getIcon('play'))
  })

  it('keeps distinct names on distinct definitions', () => {
    expect(getIcon('play')).not.toBe(getIcon('pause-circle'))
  })
})
