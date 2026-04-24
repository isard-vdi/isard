import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'

import { DesktopCard, cardSizes } from '@/components/desktop-card'

const meta = {
  component: DesktopCard,
  title: 'Desktop Card/DesktopCard',
  tags: ['autodocs', 'DesktopCard'],
  parameters: {
    design: {
      type: 'figma',
      url: ''
    },
    docs: {
      description: {
        component: `
This component contains has all the parts for a functional desktop card and only needs the desktop object to work.

To customize it, use DesktopCardBase and use slots with the different parts of the card.`
      }
    }
  },
  argTypes: {
    desktop: { control: 'object' },
    preferredViewer: {
      control: 'select',
      options: ['browser-rdp', 'browser-vnc', 'file-rdpgw', 'file-rdpvpn', 'file-spice']
    },
    size: {
      control: 'select',
      options: [...cardSizes]
    }
  },
  render: (args) => ({
    components: { DesktopCard },
    setup() {
      return { args }
    },
    template: `
      <DesktopCard :desktop="args.desktop" :preferred-viewer="args.preferredViewer" :size="args.size" />
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof DesktopCard>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args: {
    preferredViewer: 'file-spice',
    ...args
  },
  parameters: { ...parameters }
})

const baseDesktop = {
  id: '00000000-0000-0000-0000-000000000000',
  name: 'Alpine Linux',
  status: 'Stopped',
  type: 'persistent',
  template: null,
  viewers: ['browser-rdp', 'browser-vnc', 'file-rdpgw', 'file-rdpvpn', 'file-spice'],
  icon: 'linux',
  image: {
    id: '32.jpg',
    type: 'stock',
    url: `https://${window.location.hostname}:443/assets/img/desktops/stock/32.jpg`
  },
  description:
    'Lorem ipsum dolor sit amet, consectetur adipisicing elit. Praesentium inventore magnam, harum modi id, recusandae exercitationem ad repudiandae amet quidem libero rem labore possimus quod quisquam ab, distinctio laboriosam architecto.',
  ip: null,
  progress: null,
  editable: true,
  scheduled: {
    shutdown: false
  },
  server: false,
  accessed: null,
  tag: false,
  visible: null,
  user: 'local-default-admin-admin',
  group: 'default-default',
  category: 'default',
  reservables: {
    vgpus: null
  },
  interfaces: [
    {
      id: 'default',
      mac: '52:54:00:1a:19:7a'
    },
    {
      id: 'wireguard',
      mac: '52:54:00:4a:ef:ad'
    }
  ],
  current_action: null,
  storage: ['00000000-0000-0000-0000-000000000000'],
  permissions: [],
  needs_booking: false,
  next_booking_start: null,
  next_booking_end: null,
  booking_id: false,
  bastion_target: {
    http: {
      enabled: true,
      http_port: 80,
      https_port: 443
    },
    id: '00000000-0000-0000-0000-000000000000',
    ssh: {
      enabled: true,
      port: 22,
      authorized_keys: []
    },
    domain: 'example.com'
  }
}

export const Persistent = createStory({
  desktop: { ...baseDesktop, type: 'persistent' }
})
export const Temporal = createStory({
  desktop: { ...baseDesktop, type: 'nonpersistent' }
})
export const Deployment = createStory({
  desktop: { ...baseDesktop, type: 'persistent', tag: '00000000-0000-0000-0000-000000000000' }
})

export const Started = createStory({
  desktop: { ...baseDesktop, status: 'Started', ip: '12.34.56.78' }
})
export const Starting = createStory({
  desktop: { ...baseDesktop, status: 'Starting' }
})
export const ShuttingDown = createStory({
  desktop: { ...baseDesktop, status: 'Shutting-down' }
})
export const Stopping = createStory({
  desktop: { ...baseDesktop, status: 'Stopping' }
})
export const Maintenance = createStory({
  desktop: { ...baseDesktop, status: 'Maintenance' }
})

// --- Size variants ---
export const Size2xs = createStory({
  desktop: { ...baseDesktop, status: 'Started', ip: '12.34.56.78' },
  size: '2xs'
})
export const SizeXs = createStory({
  desktop: { ...baseDesktop, status: 'Started', ip: '12.34.56.78' },
  size: 'xs'
})
export const SizeSm = createStory({
  desktop: { ...baseDesktop, status: 'Started', ip: '12.34.56.78' },
  size: 'sm'
})
export const SizeMd = createStory({
  desktop: { ...baseDesktop, status: 'Started', ip: '12.34.56.78' },
  size: 'md'
})
export const SizeLg = createStory({
  desktop: { ...baseDesktop, status: 'Started', ip: '12.34.56.78' },
  size: 'lg'
})
export const SizeXl = createStory({
  desktop: { ...baseDesktop, status: 'Started', ip: '12.34.56.78' },
  size: 'xl'
})
