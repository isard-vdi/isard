import type { Meta, StoryObj } from '@storybook/vue3-vite'
import Sidebar from './Sidebar.vue'
import type { SidebarItem } from '@/lib/navigation'

const meta: Meta<typeof Sidebar> = {
  component: Sidebar,
  title: 'Navigation/Sidebar',
  tags: ['autodocs'],
  argTypes: {
    collapsed: { control: 'boolean' },
    loading: { control: 'boolean' }
  },
  render: (args) => ({
    components: { Sidebar },
    setup() {
      return {
        args
      }
    },
    template: `
      <div style="height: 100vh; display: flex;">
        <Sidebar 
          :items="args.items"
          :footerItems="args.footerItems"
          :collapsed="args.collapsed"
          :loading="args.loading"
          :user="args.user"
        >
        </Sidebar>
      </div>
    `
  })
}

const allItems: Record<string, SidebarItem> = {
  desktops: {
    key: 'desktops',
    label: 'Desktops',
    icon: 'monitor-02',
    href: '#',
    selected: true
  },
  templates: {
    key: 'templates',
    label: 'Templates',
    icon: 'colors',
    href: '',
    selected: false
  },
  media: {
    key: 'media',
    label: 'Media',
    icon: 'disc-02',
    href: '#',
    selected: false
  },
  deployments: {
    key: 'deployments',
    label: 'Deployments',
    icon: 'layout-alt-04',
    href: '#',
    selected: false
  },
  bookings: {
    key: 'bookings',
    label: 'Bookings',
    icon: 'calendar',
    href: '#',
    selected: false,
    subItems: [
      {
        key: 'summary',
        label: 'Summary',
        icon: 'bar-chart-01',
        href: '#',
        selected: false
      },
      {
        key: 'planning',
        label: 'Planning',
        icon: 'calendar-check-01',
        href: '#',
        selected: false
      }
    ]
  },
  storage: {
    key: 'storage',
    label: 'Storage',
    icon: 'save-02',
    href: '#',
    selected: false
  },
  administration: {
    key: 'administration',
    label: 'Administration',
    icon: 'settings-02',
    href: '#',
    selected: false
  }
}

const footerItems: Record<string, SidebarItem> = {
  recycleBin: {
    key: 'recycleBin',
    label: 'Recycle Bin',
    icon: 'trash-03',
    href: '#',
    badge: 5,
    selected: false
  },
  settings: {
    key: 'settings',
    label: 'Settings',
    icon: 'settings-01',
    href: '#',
    selected: false
  }
}

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    collapsed: false,
    loading: false,
    user: {
      name: 'John Doe',
      role: 'Administrator',
      photo: ''
    },
    items: Object.values(allItems),
    footerItems: Object.values(footerItems)
  }
}

export const Collapsed: Story = {
  args: {
    ...Default.args,
    collapsed: true
  }
}

export const Loading: Story = {
  args: {
    ...Default.args,
    loading: true
  }
}

export const CollapsedLoading: Story = {
  args: {
    ...Default.args,
    collapsed: true,
    loading: true
  }
}
