<script setup lang="ts">
import { computed, ref } from 'vue'
import type { HTMLAttributes } from 'vue'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  CalendarCell,
  CalendarCellTrigger,
  CalendarGrid,
  CalendarGridBody,
  CalendarGridHead,
  CalendarGridRow,
  CalendarHeadCell,
  CalendarNextButton,
  CalendarPrevButton,
  CalendarRoot
} from '@/components/ui/calendar'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger
} from '@/components/ui/select'
import { useDateFormatter } from 'reka-ui'
import { createYear, createYearRange, toDate } from 'reka-ui/date'
import { DateFormatter, getLocalTimeZone, type DateValue, today } from '@internationalized/date'
import { cn } from '@/lib/utils'
import { useI18n } from 'vue-i18n'

export interface Props {
  modelValue?: DateValue
  minValue?: DateValue
  maxValue?: DateValue
  defaultPlaceholder?: DateValue
  placeholder?: string
  class?: HTMLAttributes['class']
  locale?: string
  maxHint?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  minValue: undefined,
  maxValue: undefined,
  defaultPlaceholder: undefined,
  placeholder: 'Select date',
  class: '',
  locale: 'en-US',
  maxHint: undefined
})

const emit = defineEmits<{
  'update:modelValue': [value: DateValue | undefined]
}>()

const { t } = useI18n()
const isOpen = ref(false)
const tempValue = ref<DateValue | undefined>(props.modelValue)
const calendarModelValue = computed(() => tempValue.value as DateValue | undefined)

const resolveInitialPlaceholder = () =>
  props.modelValue ?? props.defaultPlaceholder ?? today(getLocalTimeZone())

const calendarPlaceholder = ref<DateValue>(resolveInitialPlaceholder())

const dateFormatter = computed(() => new DateFormatter(props.locale, { dateStyle: 'medium' }))
const headingFormatter = computed(() => useDateFormatter(props.locale))

const monthOptions = (date: DateValue) => createYear({ dateObj: date })

const yearOptions = computed(() =>
  createYearRange({
    start: props.minValue ?? calendarPlaceholder.value.cycle('year', -100),
    end: props.maxValue ?? calendarPlaceholder.value.cycle('year', 10)
  })
)

// Month granularity index, to compare a month against the min/max bounds
const monthIndex = (date: DateValue) => date.year * 12 + (date.month - 1)

const isMonthOptionDisabled = (monthDate: DateValue) => {
  if (props.minValue && monthIndex(monthDate) < monthIndex(props.minValue)) return true
  if (props.maxValue && monthIndex(monthDate) > monthIndex(props.maxValue)) return true
  return false
}

// Hint shown only on days past maxValue (days before minValue are disabled for another reason)
const hintForDay = (day: DateValue) =>
  props.maxHint && props.maxValue && day.compare(props.maxValue) > 0 ? props.maxHint : undefined

// Keep the visible month inside [minValue, maxValue] when navigating by dropdown
const clampPlaceholder = (candidate: DateValue) => {
  if (props.minValue && monthIndex(candidate) < monthIndex(props.minValue)) {
    return candidate.set({ year: props.minValue.year, month: props.minValue.month })
  }
  if (props.maxValue && monthIndex(candidate) > monthIndex(props.maxValue)) {
    return candidate.set({ year: props.maxValue.year, month: props.maxValue.month })
  }
  return candidate
}

const handleMonthChange = (value: unknown) => {
  if (value == null) return
  calendarPlaceholder.value = clampPlaceholder(
    calendarPlaceholder.value.set({ month: Number(value) })
  )
}

const handleYearChange = (value: unknown) => {
  if (value == null) return
  calendarPlaceholder.value = clampPlaceholder(
    calendarPlaceholder.value.set({ year: Number(value) })
  )
}

const selectedLabel = computed(() => {
  if (props.modelValue) {
    return dateFormatter.value.format(props.modelValue.toDate(getLocalTimeZone()))
  }
  return props.placeholder
})

const tempValueLabel = computed(() => {
  if (tempValue.value) {
    return dateFormatter.value.format(tempValue.value.toDate(getLocalTimeZone()))
  }
  return props.placeholder
})

const handleDateSelect = (value: DateValue | undefined) => {
  tempValue.value = value
}

const handleApply = () => {
  emit('update:modelValue', tempValue.value as DateValue | undefined)
  isOpen.value = false
}

const handleCancel = () => {
  tempValue.value = props.modelValue
  isOpen.value = false
}

const handleToday = () => {
  const now = today(getLocalTimeZone())
  tempValue.value = now
  calendarPlaceholder.value = now
}

const handleOpenChange = (open: boolean) => {
  isOpen.value = open
  if (open) {
    tempValue.value = props.modelValue
    calendarPlaceholder.value = resolveInitialPlaceholder()
  } else if (tempValue.value) {
    // Apply the date when closing the popover (click outside)
    emit('update:modelValue', tempValue.value as DateValue | undefined)
  }
}
</script>

<template>
  <Popover :open="isOpen" @update:open="handleOpenChange">
    <PopoverTrigger as-child>
      <Button
        hierarchy="secondary-gray"
        size="md"
        :class="
          cn(
            'w-full justify-start gap-2 border border-gray-warm-300 bg-base-white text-gray-warm-800 font-semibold',
            !modelValue && 'text-gray-warm-500',
            isOpen && 'ring-4 ring-brand-700/24 border-brand-700',
            props.class
          )
        "
      >
        <Icon name="calendar" size="md" class="text-gray-warm-700 shrink-0" />
        <span class="truncate">
          {{ selectedLabel }}
        </span>
      </Button>
    </PopoverTrigger>
    <PopoverContent
      class="w-80 p-0 border border-gray-warm-200 shadow-lg bg-base-white rounded-xl max-h-[50vh] overflow-auto"
      align="start"
      side="bottom"
      :side-offset="8"
      :avoid-collisions="true"
      :collision-padding="16"
      position-strategy="fixed"
    >
      <CalendarRoot
        v-slot="{ grid, weekDays, date }"
        v-model:placeholder="calendarPlaceholder"
        :model-value="calendarModelValue"
        :min-value="minValue"
        :max-value="maxValue"
        :locale="locale"
        class="px-6 py-5"
        @update:model-value="handleDateSelect"
      >
        <div class="flex flex-col gap-4">
          <!-- Header -->
          <div class="flex items-center justify-between gap-2">
            <CalendarPrevButton />
            <div class="flex items-center gap-2">
              <Select :model-value="String(date.month)" @update:model-value="handleMonthChange">
                <SelectTrigger
                  :aria-label="t('components.date-picker.month')"
                  class="h-9 w-auto gap-1 px-3 font-semibold text-gray-warm-900"
                >
                  {{ headingFormatter.custom(toDate(date), { month: 'short' }) }}
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem
                      v-for="month in monthOptions(date)"
                      :key="month.toString()"
                      :value="String(month.month)"
                      :disabled="isMonthOptionDisabled(month)"
                    >
                      {{ headingFormatter.custom(toDate(month), { month: 'long' }) }}
                    </SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
              <Select :model-value="String(date.year)" @update:model-value="handleYearChange">
                <SelectTrigger
                  :aria-label="t('components.date-picker.year')"
                  class="h-9 w-auto gap-1 px-3 font-semibold text-gray-warm-900"
                >
                  {{ headingFormatter.custom(toDate(date), { year: 'numeric' }) }}
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem
                      v-for="year in yearOptions"
                      :key="year.toString()"
                      :value="String(year.year)"
                    >
                      {{ headingFormatter.custom(toDate(year), { year: 'numeric' }) }}
                    </SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <CalendarNextButton />
          </div>

          <div class="flex gap-3 items-center">
            <div
              class="flex-1 px-3.5 py-2 bg-base-white rounded-lg shadow-sm border border-gray-warm-300 text-gray-warm-900 text-base font-normal truncate"
            >
              {{ tempValueLabel }}
            </div>
            <Button
              hierarchy="secondary-gray"
              size="md"
              type="button"
              class="px-3.5 py-2.5 font-semibold shadow-sm"
              @click="handleToday"
            >
              {{ t('components.date-picker.today') }}
            </Button>
          </div>

          <!-- Calendar grid -->
          <CalendarGrid v-for="month in grid" :key="month.value.toString()" class="w-full">
            <CalendarGridHead>
              <CalendarGridRow>
                <CalendarHeadCell v-for="day in weekDays" :key="day">
                  {{ day }}
                </CalendarHeadCell>
              </CalendarGridRow>
            </CalendarGridHead>
            <CalendarGridBody>
              <CalendarGridRow v-for="(weekDates, index) in month.rows" :key="`weekDate-${index}`">
                <CalendarCell
                  v-for="weekDate in weekDates"
                  :key="weekDate.toString()"
                  :date="weekDate"
                  :title="hintForDay(weekDate)"
                >
                  <CalendarCellTrigger :day="weekDate" :month="month.value">
                    <slot :date="weekDate">
                      {{ weekDate.day }}
                    </slot>
                  </CalendarCellTrigger>
                </CalendarCell>
              </CalendarGridRow>
            </CalendarGridBody>
          </CalendarGrid>
        </div>
      </CalendarRoot>

      <!-- Footer -->
      <div class="p-4 border-t border-gray-warm-200 flex justify-end gap-3">
        <Button
          hierarchy="secondary-gray"
          size="md"
          type="button"
          class="flex-1 font-semibold"
          @click="handleCancel"
        >
          {{ t('components.date-picker.cancel') }}
        </Button>
        <Button
          hierarchy="primary"
          size="md"
          type="button"
          class="flex-1 font-semibold"
          @click="handleApply"
        >
          {{ t('components.date-picker.apply') }}
        </Button>
      </div>
    </PopoverContent>
  </Popover>
</template>
