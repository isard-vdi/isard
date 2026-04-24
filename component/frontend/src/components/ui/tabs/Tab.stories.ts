import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { Tabs, TabsContent, TabsList, TabsTrigger } from './index'
import { ref } from 'vue'

const meta = {
  component: Tabs,
  title: 'Toggle/Tabs',
  tags: ['autodocs'],
  render: (args) => ({
    components: { Tabs, TabsContent, TabsList, TabsTrigger },
    setup() {
      const activeTab = ref(args.tabs[0].value)
      return { args, activeTab }
    },
    template: `
    <Tabs v-bind="args" v-model="activeTab">
      <TabsList class="border border-gray-warm-300 rounded-md gap-1 p-1 font-semibold">
        <TabsTrigger 
          v-for="tab in args.tabs" 
          :key="tab.value" 
          :value="tab.value"
          :icon="tab.icon"
          :count="tab.count"
          :hierarchy="tab.hierarchy"
          :isActive="activeTab === tab.value"
          @click="activeTab = tab.value"
        >
          {{ tab.value }}
        </TabsTrigger>

      </TabsList>
    </Tabs>
    `
  })
} satisfies Meta<typeof Tabs>

export default meta

type Story = StoryObj<typeof meta>

const createStory = (args: any): Story => ({ args })

export const Default = createStory({
  tabs: [
    { value: 'Instrucciones', icon: '' },
    { value: 'Recursos', icon: '' },
    { value: 'Anotaciones', icon: '' }
  ]
})

export const Alternative = createStory({
  tabs: [
    { value: 'Todos', icon: 'monitor-02', count: 5, hierarchy: 'Info' },
    { value: 'Permanentes', icon: 'browser', count: 2, hierarchy: 'Permanent' },
    { value: 'Temporales', icon: 'clock', count: 8, hierarchy: 'Temporary' },
    { value: 'Despliegues', icon: 'layout-alt-04', count: 7, hierarchy: 'Deployment' }
  ]
})
