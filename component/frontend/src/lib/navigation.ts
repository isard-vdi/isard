import type { Role } from '@/lib/auth'
import { computed, type ComputedRef } from 'vue'
import { i18n } from '@/lib/i18n'
import { useI18n } from 'vue-i18n'

// SIDEBAR ITEMS
export interface Badge {
  bgColor: string
  textColor: string
  label: number
}

export interface SidebarItem {
  key: string
  label: string
  icon?: string
  href?: string // Will use <a> tag
  route?: string // Will use the route name to navigate
  subItems?: SidebarItem[]
  selected?: boolean
  badge?: Badge
}

const sidebarItems: ComputedRef<Record<string, Record<string, SidebarItem>>> = computed(() => {
  return {
    menu: {
      desktops: {
        key: 'desktops',
        label: i18n.global.t('components.sidebar.desktops'),
        icon: 'monitor-02',
        route: 'desktops',
        selected: false
      },
      templates: {
        key: 'templates',
        label: i18n.global.t('components.sidebar.templates'),
        icon: 'colors',
        route: 'templates',
        selected: false
      },
      media: {
        key: 'media',
        label: i18n.global.t('components.sidebar.media'),
        icon: 'disc-02',
        route: 'media',
        selected: false
      },
      deployments: {
        key: 'deployments',
        label: i18n.global.t('components.sidebar.deployments.title'),
        icon: 'layout-alt-04',
        route: 'deployments',
        selected: false,
        subItems: [
          {
            key: 'deployments-list',
            label: i18n.global.t('components.sidebar.deployments.created-by-you'),
            icon: 'layers-three-01',
            route: 'deployments',
            selected: false
          },
          {
            key: 'shared-deployments',
            label: i18n.global.t('components.sidebar.deployments.shared-deployments'),
            icon: 'share-06',
            route: 'shared-deployments',
            selected: false
          }
        ]
      },
      userSharedDeployments: {
        key: 'user-shared-deployments',
        label: i18n.global.t('components.sidebar.deployments.title'),
        icon: 'layout-alt-04',
        route: 'shared-deployments',
        selected: false
      },
      bookings: {
        key: 'bookings',
        label: i18n.global.t('components.sidebar.bookings.title'),
        icon: 'calendar-date',
        route: 'booking-summary',
        selected: false,
        subItems: [
          {
            key: 'summary',
            label: i18n.global.t('components.sidebar.bookings.summary'),
            icon: 'calendar-check-01',
            route: 'booking-summary',
            selected: false
          },
          {
            key: 'planning',
            label: i18n.global.t('components.sidebar.bookings.planning'),
            icon: 'calendar-plus-02',
            route: 'planning',
            selected: false
          }
        ]
      }
    },
    footer: {
      recycleBin: {
        key: 'recycle-bin',
        label: i18n.global.t('components.sidebar.recycle-bin'),
        icon: 'trash-03',
        route: 'recycle-bin',
        badge: {
          label: 0
        }
      },
      help: {
        key: 'help',
        label: i18n.global.t('components.sidebar.help.title'),
        icon: 'help-circle',
        subItems: [
          {
            key: 'docs',
            label: i18n.global.t('components.sidebar.help.docs'),
            icon: 'book-open-01',
            href: undefined,
            selected: false
          },
          {
            key: 'viewers',
            label: i18n.global.t('components.sidebar.help.viewers'),
            icon: 'info-circle',
            href: undefined,
            selected: false
          }
        ]
      },
      administration: {
        key: 'administration',
        label: i18n.global.t('components.sidebar.administration'),
        icon: 'settings-02',
        href: '/isard-admin/admin/landing'
      }
    }
  }
})

// TODO: Remove bookings consider the user config

const sidebarItemsByRole: {
  [K in Role]: (keyof typeof sidebarItems.value.menu)[]
} = {
  admin: ['desktops', 'templates', 'media', 'deployments', 'bookings'],
  manager: ['desktops', 'templates', 'media', 'deployments', 'bookings'],
  advanced: ['desktops', 'templates', 'media', 'deployments'],
  user: ['desktops', 'bookings', 'userSharedDeployments']
}

/**
 * Get the sidebar items to show based on the user role.
 * @param role - The role of the user.
 * @param route - The current route name.
 * @param itemsInBin - The number of items in the recycle bin.
 * @param showBookingsButton - Whether to show the bookings button (from config).
 * @returns An object containing the mainItems and footerItems arrays for the sidebar.
 */
export const sidebarItemsToShow = (
  role: Role,
  route: string,
  itemsInBin: number,
  showBookingsButton = true
) => {
  let mainItems = (sidebarItemsByRole[role] || []).map((item) => {
    const menuItem = sidebarItems.value.menu[item]
    if (!menuItem.subItems) {
      if (menuItem.route === route) {
        return { ...menuItem, selected: true }
      }
      return menuItem
    }
    const subItems = menuItem.subItems.map((subItem) =>
      subItem.route === route ? { ...subItem, selected: true } : { ...subItem, selected: false }
    )
    const isParentSelected = subItems.some((subItem) => subItem.selected)
    return { ...menuItem, selected: isParentSelected, subItems }
  })

  if (!showBookingsButton) {
    mainItems = mainItems.filter((item) => item.key !== 'bookings')
  }

  mainItems = mainItems.map((item) => {
    if (item.key === 'bookings' && role !== 'admin') {
      // For non-admin users, remove subitems and just navigate directly to summary
      return {
        ...item,
        subItems: undefined,
        route: 'booking-summary'
      }
    }
    return item
  })

  const footerItems = Object.values(sidebarItems.value.footer)
    .filter((item) => {
      if (item.key === 'administration') {
        return role === 'admin' || role === 'manager'
      }
      return true
    })
    .map((item) => {
      if (item.key === 'recycle-bin') {
        return {
          ...item,
          badge: {
            bgColor: itemsInBin > 0 ? 'bg-error-600' : 'bg-gray-50',
            textColor: itemsInBin > 0 ? 'text-base-white' : 'text-slate-700',
            label: itemsInBin
          }
        }
      }
      return item
    })

  return { mainItems, footerItems }
}

// TOPBAR ITEMS

export interface TopBarItem {
  key: string
  label: string
  icon?: string
  href?: string // Will use <a> tag
  to?: string // Will use the route name to navigate
  subItems?: TopBarItem[]
}

const topBarItemsByRole: Record<string, string[]> = {
  admin: [
    'desktops',
    'templates',
    'media',
    'deployments',
    'labs-list',
    'bookings',
    'storage',
    'administration'
  ],
  manager: [
    'desktops',
    'templates',
    'media',
    'deployments',
    'labs-list',
    'bookings',
    'storage',
    'administration'
  ],
  advanced: ['desktops', 'templates', 'media', 'deployments', 'labs-list', 'storage'],
  user: ['desktops', 'bookings', 'labs-user', 'storage']
}

/**
 * Get the top bar items based on the user role.
 * @param role - The role of the user.
 * @returns An object containing the mainItems array for the top bar.
 */
export function getRoleTopBarItems(role: Role) {
  const { t } = useI18n()

  const allItems: Record<string, TopBarItem> = {
    desktops: {
      key: 'desktops',
      label: t('components.sidebar.desktops'),
      icon: 'monitor-02',
      href: '/desktops'
    },
    templates: {
      key: 'templates',
      label: t('components.sidebar.templates'),
      icon: 'colors',
      href: '/templates'
    },
    media: {
      key: 'media',
      label: t('components.sidebar.media'),
      icon: 'disc-02',
      href: '/media'
    },
    deployments: {
      key: 'deployments',
      label: t('components.sidebar.deployments.title'),
      icon: 'layout-alt-04',
      href: '/deployments'
    },
    'labs-list': {
      // TODO: rename to 'deployments' after moving deployments code to apiv4
      key: 'labs-list',
      label: t('components.sidebar.labs'),
      icon: 'beaker-02',
      to: 'labs-list'
    },
    'labs-user': {
      // TODO: rename to 'labs' after moving deployments code to apiv4
      key: 'labs-user',
      label: t('components.sidebar.labs'),
      icon: 'beaker-02',
      to: 'labs-user'
    },
    bookings: {
      key: 'bookings',
      label: t('components.sidebar.bookings.title'),
      icon: 'calendar',
      to: 'booking-summary',
      subItems: [
        {
          key: 'summary',
          label: t('components.sidebar.bookings.summary'),
          to: 'booking-summary'
        },
        {
          key: 'planning',
          label: t('components.sidebar.bookings.planning'),
          to: 'planning'
        }
      ]
    },
    storage: {
      key: 'storage',
      label: t('components.sidebar.storage'),
      icon: 'save-02',
      href: '/storage'
    },
    administration: {
      key: 'administration',
      label: t('components.sidebar.administration'),
      icon: 'settings-02',
      href: '/isard-admin/admin/landing'
    }
  }

  const mainItems = topBarItemsByRole[role]?.map((key) => allItems[key]) ?? []

  return {
    mainItems
  }
}
