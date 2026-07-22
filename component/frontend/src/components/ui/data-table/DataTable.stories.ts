import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import {
  DataTableBackground,
  DataTable,
  DataTableBody,
  DataTableCell,
  DataTableHeaderRow,
  DataTableRow,
  DataTableHead,
  DataTableEmpty
} from '@/components/ui/data-table'

const meta = {
  // component: DataTable,
  title: 'DataTable/Base',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=8940-18816&m=dev'
    },
    docs: {
      description: {
        component:
          'This is a base example of a table without any logic. check out `@/components/data-table/DataTable.vue` for a more complete example.'
      }
    }
  },
  argTypes: {},
  render: (args) => ({
    components: {
      DataTableBackground,
      DataTable,
      DataTableBody,
      DataTableCell,
      DataTableHeaderRow,
      DataTableRow,
      DataTableHead,
      DataTableEmpty
    },
    setup() {
      return {
        args
      }
    },
    template: `
      <DataTableBackground>
        <DataTable
          :template-cols="[
            'minmax(var(--spacing-48), 1fr)',
            'minmax(var(--spacing-48), 1fr)',
            'min-content'
          ]"
        >
          <DataTableHeaderRow>
            <DataTableHead
              :sortable="true"
            >
              sortable
            </DataTableHead>
            <DataTableHead>
              Non sortable
            </DataTableHead>
            <DataTableHead>
              Id
            </DataTableHead>
          </DataTableHeaderRow>

          <DataTableBody>
            <DataTableRow
              v-for="(row, rowIndex) in [
                { id: 1, name: 'Row 1', info: 'Some info 1' },
                { id: 2, name: 'Row 2', info: 'Some info 2' },
                { id: 3, name: 'Row 3', info: 'Some info 3' }
              ]"
              :key="row.id"
            >
              <DataTableCell>
                {{ row.name }}
              </DataTableCell>
              <DataTableCell>
                {{ row.info }}
              </DataTableCell>
              <DataTableCell>
                {{ row.id }}
              </DataTableCell>
            </DataTableRow>
          </DataTableBody>
        </DataTable>

        <template #pagination>
          Pagination slot
        </template>
      </DataTableBackground>
    `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof DataTable>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({})
