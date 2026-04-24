import { test as base, loginHelpers } from './login.js'

const desktopsData = {
  test: {
    id: 'dae8fee5-93d6-4f80-ae0c-121d304910e4',
    name: 'Desktop with storage',
    status: 'Stopped',
    persistent: true,
    type: 'persistent',
    viewers: ['browser-vnc', 'file-spice'],
    create_dict: {
      reservables: {
        vgpus: null
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default"
  },

  gpu: {
    id: '3c6b1eaa-2d4f-4f43-9f87-2b1ac2c3d4e5',
    name: 'Test desktop with GPU',
    status: 'Stopped',
    persistent: true,
    type: 'persistent',
    viewers: ['browser-rdp', 'file-spice'],
    needs_booking: true,
    create_dict: {
      reservables: {
        vgpus: ['NVIDIA-A16-2Q']
      },
      hardware: {
        interfaces: [
          {
            id: 'wireguard',
            mac: '52:54:00:a1:b2:c3'
          }
        ]
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default"
  },

  booked: {
    id: '7a9d3c12-1b23-4a56-8c9d-0e1f2a3b4c5d',
    name: 'Booked desktop',
    status: 'Stopped',
    persistent: true,
    type: 'persistent',
    viewers: ['file-rdpvpn', 'browser-vnc'],
    needs_booking: true,
    booking_id: '0a1b2c3d-4e5f-6789-abcd-ef0123456789',
    create_dict: {
      reservables: {
        vgpus: ['NVIDIA-A16-2Q']
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default"
  },

  failed: {
    id: '8b7c6d5e-4f3a-2b1c-9d8e-7f6a5b4c3d2e',
    name: 'Failed desktop',
    status: 'Failed',
    persistent: true,
    type: 'persistent',
    viewers: ['browser-vnc', 'file-spice'],
    create_dict: {
      reservables: {
        vgpus: null
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default"
  },

  maintenance: {
    id: '1f2e3d4c-5b6a-7c8d-9e0f-a1b2c3d4e5f6',
    name: 'Test maintenance desktop',
    status: 'Maintenance',
    persistent: true,
    type: 'persistent',
    current_action: 'increase',
    viewers: ['browser-vnc', 'browser-rdp'],
    create_dict: {
      reservables: {
        vgpus: null
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default"
  },

  started: {
    id: '9a8b7c6d-5e4f-3a2b-1c9d-8e7f6a5b4c3d',
    name: 'Test started desktop',
    status: 'Started',
    persistent: true,
    type: 'persistent',
    viewers: ['file-rdpgw', 'browser-vnc'],
    ip: '10.2.0.100',
    create_dict: {
      reservables: {
        vgpus: null
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default"
  },

  downloading: {
    id: '2f1a7d4b-09d4-4b7b-8a1a-2d6b0f0f1234',
    name: 'Downloading desktop',
    status: 'Downloading',
    persistent: true,
    type: 'persistent',
    progress: {
      percentage: 42
    },
    viewers: ['browser-vnc', 'browser-rdp'],
    create_dict: {
      reservables: {
        vgpus: null
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default"
  },

  unknown: {
    id: '5b4c3d2e-1f0a-4c9b-9d2e-1a2b3c4d5e6f',
    name: 'Unknown status',
    status: 'Unknown',
    persistent: true,
    type: 'persistent',
    viewers: ['file-spice'],
    create_dict: {
      reservables: {
        vgpus: null
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default"
  }
  ,
  recreable: {
    id: 'a1b2c3d4-5e6f-7a8b-9c0d-e1f2a3b4c5d6',
    name: 'Recreable Desktop Test',
    status: 'Stopped',
    persistent: true,
    type: 'non-persistent',
    viewers: ['browser-vnc', 'file-spice'],
    tag: 'deployment-test-001',
    tag_name: 'Deployment-Test-Frontend',
    tag_visible: true,
    create_dict: {
      reservables: {
        vgpus: null
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default",
    os: 'linux'
  },
  temporary: {
    id: 'b2c3d4e5-6f7a-8b9c-0d1e-2f3a4b5c6d7e',
    name: 'Temporary Desktop',
    status: 'Started',
    persistent: false,
    type: 'non-persistent',
    viewers: ['browser-vnc', 'file-spice'],
    create_dict: {
      reservables: {
        vgpus: null
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default",
    os: 'linux'
  },
  notEnoughAdvancedTime: {
    id: 'test-desktop-not-enough-advanced-time',
    name: 'Test Not Enough Advanced Time',
    status: 'Stopped',
    persistent: true,
    type: 'persistent',
    needs_booking: true,
    viewers: ['browser-vnc', 'file-spice'],
    create_dict: {
      reservables: {
        vgpus: ['NVIDIA-T4-2Q']
      }
    },
    user: "4dffb235-8293-4e40-b661-25ab33cf1781",
    username: "user01",
    category: "default",
    group: "default-default",
    os: 'linux'
  },
  gpuUnavailable: {
    id: 'test-desktop-gpu-unavailable',
    name: 'Test GPU Unavailable',
    status: 'Stopped',
    persistent: true,
    type: 'persistent',
    needs_booking: true,
    viewers: ['browser-vnc', 'file-spice'],
    create_dict: {
      reservables: {
        vgpus: ['NVIDIA-A16-4Q']
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default",
    os: 'linux'
  },
  bastion: {
    id: '3a1f2b4c-6d78-4e90-9a12-b3c4d5e6f7a8',
    name: 'Desktop with Bastion',
    status: 'Stopped',
    persistent: true,
    type: 'persistent',
    viewers: ['browser-vnc', 'file-spice'],
    bastion_target: {
      id: '3a1f2b4c-6d78-4e90-9a12-b3c4d5e6f7a8',
      domain: null,
      http: {
        enabled: true,
        http_port: 80,
        https_port: 443
      },
      ssh: {
        enabled: true,
        port: 22,
        authorized_keys: 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKey test@example.com'
      }
    },
    create_dict: {
      reservables: {
        vgpus: null
      },
      hardware: {
        interfaces: [
          {
            id: 'wireguard',
            mac: '52:54:00:ba:57:10'
          }
        ]
      }
    },
    user: "local-default-admin-admin",
    category: "default",
    group: "default-default",
    os: 'linux'
  }

}

// Maps each desktop key to its owner user key (for parallel test isolation)
const desktopOwners = {
  gpu: 'admin_e2e_01',
  booked: 'admin_e2e_02',
  failed: 'admin_e2e_03',
  maintenance: 'admin_e2e_04',
  downloading: 'admin_e2e_05',
  unknown: 'admin_e2e_06',
  recreable: 'admin_e2e_07',
  bastion: 'admin_e2e_08',
  test: 'admin_e2e_09',
  gpuUnavailable: 'admin_e2e_10',
  temporary: 'admin_e2e_11',
  started: 'admin_e2e_12',
}

const desktopsURL = '/frontend/desktops';
// TODO: change to /desktops when that becomes the default landing page after login !!

const desktopHelpers = {
  async loginAndGoToDesktops(page, user, categories) {
    const category = categories[user.category]

    // If category is hidden (frontend=false), always use direct URL
    if (!category.frontend) {
      await page.goto(`/login/all/${category.url}`)
    } else {
      await page.goto('/login')

      const visibleCategoriesCount = Object.values(categories).filter((cat) => cat.frontend).length
      if (visibleCategoriesCount > 1) {
        const categorySelector = page.locator('div.flex.flex-col.space-y-4 [role="combobox"]').first()
        await categorySelector.waitFor({ state: 'visible', timeout: 5000 })
        await categorySelector.click()
        await page.waitForTimeout(500)

        const option = page.locator(`[role="option"]:has-text("${category.name}"), li:has-text("${category.name}")`).first()
        await option.waitFor({ state: 'visible', timeout: 5000 })
        await option.click()
        await page.waitForTimeout(500)
      }
    }

    await loginHelpers.fillLoginForm(page, user)

    await page.waitForTimeout(2000)

    const current = page.url()
    if (current.includes('//desktops')) {
      await page.goto(desktopsURL)
    } else if (!current.includes(desktopsURL)) {
      await page.goto(desktopsURL)
    }
  },

  async waitForDesktopsPageLoad(page) {

    await page.waitForURL(desktopsURL, { timeout: 15000 })

    // If we're not exactly on /desktops, navigate there
    const currentUrl = page.url()
    if (!currentUrl.includes(desktopsURL)) {
      await page.goto(desktopsURL)
      await page.waitForLoadState('networkidle')
    }

    try {
      await page.waitForSelector('main, [role="main"], .main-content', { timeout: 5000 })
    } catch (error) {
      await page.waitForSelector('body', { timeout: 5000 })
    }

    await page.waitForTimeout(1000)
  }
}

export const test = base.extend({
  desktopsData: async ({ }, use) => {
    await use(desktopsData)
  },

  desktopOwners: async ({ }, use) => {
    await use(desktopOwners)
  },

  desktopHelpers: async ({ }, use) => {
    await use(desktopHelpers)
  },
})

export { expect } from '@playwright/test'
