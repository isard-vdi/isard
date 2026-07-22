import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Card } from './index'
import mountains from '@/assets/img/mountains.svg'

function getButtons(args: any) {
  if (args.kind === 'lab') {
    return [
      {
        label: 'components.card.button.enter',
        hierarchy: 'primary',
        icon: 'log-in-04',
        iconStrokeColor: 'var(--base-white)'
      }
    ]
  } else if (args.status === 'Started') {
    const viewerLabel = args.preferredViewer
      ? `components.card.button.viewer-title.${args.preferredViewer}`
      : 'components.card.button.' + args.viewers[0]

    return [
      // SHUTDOWN BUTTON
      {
        label: 'components.card.button.shutdown',
        hierarchy: 'destructive',
        icon: 'stop',
        iconStrokeColor: 'var(--base-white)',
        iconFillColor: 'var(--red-500)'
      },
      // ENTER WITH VIEWER BUTTON
      {
        label: 'components.card.button.enter-with',
        hierarchy: 'primary',
        iconStrokeColor: 'var(--base-white)',
        icon: 'arrow-right'
      },
      // VIEWER BUTTON
      {
        hierarchy: 'primary',
        icon: 'settings-01',
        iconStrokeColor: 'var(--base-white)'
      }
      // TODO: Add viewer dropdown with args.viewers
    ]
  } else if (args.needsBooking) {
    return [
      // BOOKING BUTTON
      {
        label: 'components.card.button.book',
        hierarchy: 'tertiary-color',
        icon: 'calendar-plus-02',
        iconStrokeColor: 'var(--warning-700)'
      }
    ]
  } else {
    return [
      // START BUTTON
      {
        label: 'components.card.button.start',
        hierarchy: 'primary',
        icon: 'play',
        iconStrokeColor: 'var(--base-white)',
        iconFillColor: 'var(--brand-800)'
      }
    ]
  }
}

const meta: Meta<typeof Card> = {
  title: 'Card/Card',
  component: Card,
  tags: ['autodocs'],
  argTypes: {
    kind: {
      control: 'select',
      options: ['persistent', 'volatile', 'deployment', 'lab']
    },
    status: {
      control: 'select',
      options: ['Started', 'Stopped', 'Starting', 'Stopping']
    },
    preferredViewer: {
      control: 'select',
      options: ['file-spice', 'file-rdpvpn', 'file-rdpgw', 'browser-vnc', 'browser-rdp']
    }
  },
  render: (args) => ({
    components: {
      Card
    },
    setup() {
      return { args, buttons: getButtons(args) }
    },
    template: `<div class="w-full flex justify-center">
      <Card 
        :kind="args.kind"
        :title="args.title"
        :description="args.description"
        :background-image="args.backgroundImage"
        :status="args.status"
        :desktopShutdown="args.shutdownTime ? true : false"
        :shutdownTime="args.shutdownTime"
        :viewers="args.viewers"
        :preferred-viewer="args.preferredViewer"
        :needsBooking="args.needsBooking"
        :icon="'info-circle'"
        :buttons="buttons"
      />
    </div>`
  })
}

export default meta

export const Persistent: StoryObj<typeof meta> = {
  args: {
    kind: 'persistent',
    status: 'Stopped',
    viewers: ['file-spice', 'file-rdpvpn', 'file-rdpgw'],
    preferredViewer: 'file-rdpgw',
    title: 'Ubuntu 22.04',
    description: 'This is a persistent desktop',
    needsBooking: false,
    backgroundImage: mountains
  }
}

export const Lab: StoryObj<typeof meta> = {
  args: {
    kind: 'lab',
    status: 'Stopped',
    viewers: ['file-spice', 'file-rdpvpn', 'file-rdpgw'],
    preferredViewer: 'file-rdpgw',
    title: 'Client Server Lab',
    description: 'This is a lab',
    needsBooking: false,
    backgroundImage: mountains,
    desktopsCount: 3
  }
}

export const PersistentStarted: StoryObj<typeof meta> = {
  args: {
    kind: 'persistent',
    status: 'Started',
    viewers: ['file-spice', 'browser-rdp'],
    preferredViewer: 'browser-rdp',
    title: 'Ubuntu 22.04',
    description: 'This is a started persistent desktop',
    needsBooking: false,
    shutdownTime: '12:00',
    backgroundImage: mountains
  }
}

export const Booking: StoryObj<typeof meta> = {
  args: {
    kind: 'persistent',
    status: 'Stopped',
    viewers: ['file-spice', 'browser-vnc'],
    preferredViewer: 'browser-vnc',
    title: 'Ubuntu 22.04 with GPU',
    description: 'This is a persistent desktop who needs booking',
    needsBooking: true,
    backgroundImage: mountains
  }
}

export const TemporaryDesktop: StoryObj<typeof meta> = {
  args: {
    kind: 'volatile',
    status: 'Started',
    viewers: ['file-spice', 'file-rdpgw'],
    preferredViewer: 'file-spice',
    title: 'Fedora 38',
    description: 'This desktop will be deleted when it is stopped',
    needsBooking: false,
    backgroundImage: mountains
  }
}

export const FromDeployment: StoryObj<typeof meta> = {
  args: {
    kind: 'deployment',
    status: 'Stopped',
    viewers: ['file-spice'],
    preferredViewer: 'file-spice',
    title: 'Ubuntu 22.04 from deployment',
    description: 'This is a desktop from deployment',
    needsBooking: false,
    backgroundImage: mountains
  }
}
