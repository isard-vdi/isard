import type { ComponentPropsAndSlots, Meta, StoryObj } from '@storybook/vue3-vite'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell
} from '@/components/ui/table'
const props = [
  {
    id: 1,
    repeat: false,
    name: 'Visibilidad',
    contentType: 'Badge',
    content: ['Visible', 'Oculto', 'Visible']
  },
  {
    id: 2,
    repeat: false,
    name: 'Despliegue',
    contentType: 'div',
    content: ['Despliegues alumnos 1A', 'Despliegues alumnos 1B', 'Diseño industrial 3d']
  },
  {
    id: 3,
    repeat: true,
    name: '',
    contentType: 'DropdownButton',
    content: [
      { icon: 'edit-01', text: 'Editar despliegue' },
      { icon: 'download-02', text: 'Descargar visor directo' },
      { icon: 'link-01', text: 'Enlace en directo' },
      { icon: 'refresh-cw-04', text: 'Recrear despliegue' },
      { icon: 'calendar', text: 'Reservar' },
      { icon: 'trash-04', text: 'Eliminar' }
    ]
  }
]

const meta = {
  component: Table,
  title: 'Table',
  tags: ['autodocs'],
  parameters: {
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/FHPNZiT08g7iQysunKZkLm/N%C3%89FIX---ISARD-Design-system-Cliente?node-id=8940-18816&m=dev'
    }
  },
  argTypes: {},
  render: (args) => ({
    components: { Table, TableHeader, TableBody, TableRow, TableHead, TableCell },
    setup() {
      return {
        args
      }
    },
    template: `
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead v-for=props/>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    <TableRow>
                        <TableCell>
                        dad sdfad
                        </TableCell>
                        <TableCell>
                        dad
                        </TableCell>
                        <TableCell>
                        hey
                        </TableCell>
                    </TableRow>
                    <TableRow>
                        <TableCell>
                        1dad sdfad
                        </TableCell>
                        <TableCell>
                        2dad
                        </TableCell>
                        <TableCell>
                        hola
                        </TableCell>
                    </TableRow>
                </TableBody>
            </Table>
        `
  })
} satisfies Meta<ComponentPropsAndSlots<typeof Table>>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any, parameters?: any): Story => ({
  args,
  parameters
})

export const Default = createStory({})
