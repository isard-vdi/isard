import { describe, expect, it } from 'vitest'

import { UNUSABLE_TEMPLATE_STATUSES, isTemplateFailed, isTemplateNotReady } from './status'

// Drives the deployment/desktop template selector: a not-ready template must
// not be selectable.
describe('isTemplateNotReady', () => {
  it.each(['CreatingTemplate', 'Failed', 'Maintenance', 'DownloadStarting', 'Downloading'])(
    'blocks selecting a %s template',
    (status) => {
      expect(isTemplateNotReady({ status })).toBe(true)
    }
  )

  it.each(['Stopped', 'Started'])('allows selecting a %s template', (status) => {
    expect(isTemplateNotReady({ status })).toBe(false)
  })
})

describe('UNUSABLE_TEMPLATE_STATUSES', () => {
  it('is exactly the five not-ready statuses the backend rejects', () => {
    expect([...UNUSABLE_TEMPLATE_STATUSES].sort()).toEqual(
      ['CreatingTemplate', 'DownloadStarting', 'Downloading', 'Failed', 'Maintenance'].sort()
    )
  })

  it('still covers the plain failed case (superset of isTemplateFailed)', () => {
    expect(isTemplateFailed({ status: 'Failed' })).toBe(true)
    expect(isTemplateNotReady({ status: 'Failed' })).toBe(true)
  })
})
