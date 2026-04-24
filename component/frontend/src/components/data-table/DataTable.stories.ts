import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import { DataTable } from '@/components/data-table'
import { Badge } from '@/components/badge'
import { BadgeInfo } from '@/components/badge/info'
import { DropdownButton } from '@/components/dropdown-button'
import Icon from '@/components/icon/Icon.vue'

const meta = {
  component: DataTable,
  title: 'DataTable/Automatic',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=9163-98690&t=0QEhThFKd6fZdwQK-1'
    }
  },
  argTypes: {
    headers: {
      control: 'object',
      description: 'Defines the headers of the data table',
      defaultValue: []
    },
    rows: {
      control: 'object',
      description: 'Defines the rows of the data table',
      defaultValue: []
    },
    pageSize: {
      control: 'number',
      description: 'Defines number of rows per page',
      defaultValue: 10
    }
  },
  render: (args) => ({
    components: { DataTable, Badge, BadgeInfo, DropdownButton, Icon },
    setup() {
      return {
        args
      }
    },
    template: `
      <DataTable v-bind="args">
        <template #cell-visibility="{ value }">
          <Badge v-if="value"
            color="blue"
            shape="rounded"
            icon="eye"
            content="Visible"
          />
          <Badge v-else
            color="gray"
            shape="rounded"
            icon="eye-off"
            content="Hidden"
          />
        </template>
        <template #cell-startedDesktops="{ value }">
          <BadgeInfo
            icon="power-01"
            :content="value"
          />
        </template>
        <template #cell-visibleDesktops="{ value }">
          <BadgeInfo
            icon="eye"
            :content="value"
          />
        </template>
        <template #cell-total="{ value }">
          <BadgeInfo
            icon="monitor-02"
            :content="value"
          />
        </template>
        <template #cell-actions="{ value }">
          <DropdownButton :menuContent="value" />
        </template>
      </DataTable>
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof DataTable>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args: { ...args },
  parameters: { ...parameters }
})

// TODO: Review actions definition
const actions = [
  { icon: 'edit-01', textKey: 'Edit deployment' },
  { icon: 'link-01', textKey: 'Direct viewer' },
  { icon: 'refresh-cw-04', textKey: 'Recreate' },
  { icon: 'calendar', textKey: 'Book' },
  { icon: 'trash-04', textKey: 'Delete' }
]

export const Default = createStory({
  headers: [
    { name: 'Visibility', key: 'visibility', width: 'min-content' },
    { name: 'Description', key: 'description' },
    {
      name: 'Desktop name',
      key: 'desktopName',
      width: 'minmax(var(--spacing-48), var(--spacing-192))'
    },
    { name: 'Started desktops', key: 'startedDesktops', width: 'min-content' },
    { name: 'Visible desktops', key: 'visibleDesktops', width: 'max-content' },
    { name: 'Total', key: 'total', width: 'min-content' },
    { name: 'Actions', key: 'actions', width: 'min-content' }
  ],
  rows: [
    {
      visibility: true,
      description: 'Student deployment 1A',
      desktopName: 'Ubuntu 22.04 Client, Ubuntu Server',
      startedDesktops: '1',
      visibleDesktops: '3',
      total: '3',
      actions: actions
    },
    {
      visibility: false,
      description: 'Student deployment 1A',
      desktopName: 'Ubuntu 22.04',
      startedDesktops: '2',
      visibleDesktops: '2',
      total: '3',
      actions: actions
    },
    {
      visibility: true,
      description: 'Programming 101',
      desktopName: 'Debian 11 A, Debian 11 B, Debian 11 C',
      startedDesktops: '8',
      visibleDesktops: '10',
      total: '12',
      actions: actions
    },
    {
      visibility: false,
      description: 'Data Science Lab',
      desktopName: 'Ubuntu 23.04, Win 11',
      startedDesktops: '0',
      visibleDesktops: '0',
      total: '8',
      actions: actions
    },
    {
      visibility: true,
      description: 'Cybersecurity Training',
      desktopName: 'Kali Linux, Ubuntu attacker',
      startedDesktops: '15',
      visibleDesktops: '15',
      total: '20',
      actions: actions
    },
    {
      visibility: true,
      description: 'Design Workshop',
      desktopName: 'Windows 11',
      startedDesktops: '4',
      visibleDesktops: '6',
      total: '6',
      actions: actions
    },
    {
      visibility: true,
      description: 'Engineering Workstations',
      desktopName: 'CentOS 9',
      startedDesktops: '5',
      visibleDesktops: '5',
      total: '5',
      actions: actions
    },
    {
      visibility: false,
      description: 'Admin Workstations',
      desktopName: 'Fedora 38',
      startedDesktops: '1',
      visibleDesktops: '0',
      total: '4',
      actions: actions
    },
    {
      visibility: true,
      description: 'Web Development Course',
      desktopName: 'Ubuntu 22.04, Ubuntu web server',
      startedDesktops: '12',
      visibleDesktops: '15',
      total: '15',
      actions: actions
    },
    {
      visibility: false,
      description: 'Research Team',
      desktopName: 'Arch Linux',
      startedDesktops: '3',
      visibleDesktops: '0',
      total: '7',
      actions: actions
    },
    {
      visibility: true,
      description: 'AI Training Lab',
      desktopName: 'Ubuntu with GPU support, Ubuntu with CPU support,',
      startedDesktops: '6',
      visibleDesktops: '10',
      total: '10',
      actions: actions
    },
    {
      visibility: true,
      description: 'Art Department',
      desktopName: 'Ventura',
      startedDesktops: '5',
      visibleDesktops: '9',
      total: '9',
      actions: actions
    }
  ]
})
