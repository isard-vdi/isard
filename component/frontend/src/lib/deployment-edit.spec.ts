import { describe, expect, it } from 'vitest'

import type { DeploymentResponse } from '@/gen/oas/apiv4'
import { startedDesktopCount } from './deployment-edit'

const deployment = (statuses: (string | null)[]): DeploymentResponse =>
  ({
    info: {},
    users: [
      {
        id: 'user',
        name: 'Ada',
        username: 'ada',
        desktops: statuses.map((status, index) => ({
          desktop_id: `desktop-${index}`,
          name: `Desktop ${index}`,
          status
        }))
      }
    ]
  }) as unknown as DeploymentResponse

describe('startedDesktopCount', () => {
  it('counts every status the API rejects the edit for', () => {
    const blocking = ['Started', 'Starting', 'Stopping', 'Shutting-down', 'Paused', 'CreatingDisk']
    expect(startedDesktopCount(deployment(blocking))).toBe(blocking.length)
  })

  it('leaves out the ones the API accepts', () => {
    expect(startedDesktopCount(deployment(['Stopped', 'Failed', 'Unknown', null]))).toBe(0)
    expect(startedDesktopCount(undefined)).toBe(0)
  })
})
