import type { Meta, StoryObj } from '@storybook/vue3-vite'
import DatePicker from './DatePicker.vue'
import { ref } from 'vue'
import { today, getLocalTimeZone } from '@internationalized/date'

const meta = {
  title: 'Components/DatePicker',
  component: DatePicker,
  parameters: {
    layout: 'centered',
    design: {
      type: 'figma',
      url: 'https://www.figma.com/design/kZGlXBMDzC0kVb3BMl7j7x/NAOMI--ISARD-Design-system-Cliente?node-id=1150-16803&m=dev'
    }
  },
  tags: ['autodocs'],
  argTypes: {
    placeholder: {
      control: 'text',
      description: 'Placeholder text when no date is selected'
    },
    locale: {
      control: 'select',
      options: ['en-US', 'es-ES', 'ca-ES', 'fr-FR', 'de-DE', 'it-IT', 'pt-PT'],
      description: 'Locale for date formatting'
    }
  },
  args: {
    placeholder: 'Select date',
    locale: 'en-US'
  }
} satisfies Meta<typeof DatePicker>

export default meta
type Story = StoryObj<typeof meta>

/**
 * Basic date picker with default settings.
 * Allows selecting any date.
 */
export const Default: Story = {
  render: (args) => ({
    components: { DatePicker },
    setup() {
      const selectedDate = ref(null)

      return { args, selectedDate }
    },
    template: `
      <div class="w-80">
        <DatePicker 
          v-model="selectedDate"
          :placeholder="args.placeholder"
          :locale="args.locale"
        />
        <p class="mt-4 text-sm text-gray-warm-700">
          Selected: {{ selectedDate ? selectedDate.toString() : 'None' }}
        </p>
      </div>
    `
  })
}

/**
 * Date picker with minimum and maximum date constraints.
 * Only allows selecting dates from tomorrow to one year ahead.
 */
export const WithMinMax: Story = {
  render: (args) => ({
    components: { DatePicker },
    setup() {
      const selectedDate = ref(null)
      const tz = getLocalTimeZone()

      // Min: tomorrow
      const tomorrow = today(tz).add({ days: 1 })

      // Max: one year from now
      const maxDate = today(tz).add({ years: 1 })

      return { args, selectedDate, tomorrow, maxDate }
    },
    template: `
      <div class="w-80">
        <DatePicker 
          v-model="selectedDate"
          :min-value="tomorrow"
          :max-value="maxDate"
          :placeholder="args.placeholder"
          :locale="args.locale"
        />
        <p class="mt-4 text-sm text-gray-warm-700">
          Selected: {{ selectedDate ? selectedDate.toString() : 'None' }}
        </p>
        <p class="mt-2 text-xs text-gray-warm-500">
          Min: Tomorrow | Max: +1 year
        </p>
      </div>
    `
  })
}

/**
 * Date picker with a pre-selected date.
 * Useful for editing existing dates.
 */
export const WithDefaultValue: Story = {
  render: (args) => ({
    components: { DatePicker },
    setup() {
      const tz = getLocalTimeZone()
      const selectedDate = ref(today(tz).add({ months: 1 }))

      return { args, selectedDate }
    },
    template: `
      <div class="w-80">
        <DatePicker 
          v-model="selectedDate"
          :placeholder="args.placeholder"
          :locale="args.locale"
        />
        <p class="mt-4 text-sm text-gray-warm-700">
          Selected: {{ selectedDate ? selectedDate.toString() : 'None' }}
        </p>
      </div>
    `
  })
}

/**
 * Date picker with Spanish locale.
 * Shows how date formatting changes with different locales.
 */
export const SpanishLocale: Story = {
  render: () => ({
    components: { DatePicker },
    setup() {
      const selectedDate = ref(null)
      const tz = getLocalTimeZone()
      const defaultDate = today(tz).add({ months: 1 })

      return { selectedDate, defaultDate }
    },
    template: `
      <div class="w-80">
        <DatePicker 
          v-model="selectedDate"
          :default-placeholder="defaultDate"
          placeholder="Selecciona una fecha"
          locale="es-ES"
        />
        <p class="mt-4 text-sm text-gray-warm-700">
          Seleccionado: {{ selectedDate ? selectedDate.toString() : 'Ninguno' }}
        </p>
      </div>
    `
  })
}
