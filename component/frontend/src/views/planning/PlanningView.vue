<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

import BookingCalendar from '@/components/booking/BookingCalendar.vue'
import type { CalendarView, CalendarSplit } from '@/components/booking/BookingCalendar.vue'
import PlanningEventModal from '@/components/planning/PlanningEventModal.vue'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import type { CalendarEvent } from '@/lib/booking/adapter'
import {
  formatAsDate,
  formatAsLocalDateTime,
  formatAsTime,
  localTimeToUtc,
  nextSunday,
  pastMonday
} from '@/lib/booking/date-utils'
import { usePlanningStore, type PlanningEventDraft } from '@/stores/planning'
import {
  useReservableTypes,
  useReservableItems,
  useReservableSubitems,
  useItemPlans
} from '@/composables/usePlanningData'
import { usePlanningMutations } from '@/composables/usePlanningMutations'
import { describeApiError } from '@/lib/api-errors'

const i18n = useI18n()
const { t } = i18n
const planningStore = usePlanningStore()

const initialStart = localTimeToUtc(formatAsLocalDateTime(pastMonday()))
const initialEnd = localTimeToUtc(formatAsLocalDateTime(nextSunday()))

planningStore.setView({
  timeframe: 'week',
  start: initialStart,
  end: initialEnd
})

const range = ref({ start: initialStart, end: initialEnd })

const selectedType = computed({
  get: () => planningStore.selectedReservableType,
  set: (value: string) => planningStore.setReservableType(value)
})
const selectedItemId = computed({
  get: () => planningStore.selectedReservableItemId,
  set: (value: string) => planningStore.setReservableItem(value)
})

const { types } = useReservableTypes()
const reservableTypeRef = computed(() => selectedType.value)
const reservableItemIdRef = computed(() => selectedItemId.value)
const { items } = useReservableItems(reservableTypeRef)
const { subitems } = useReservableSubitems(reservableTypeRef, reservableItemIdRef)
const { events } = useItemPlans(reservableItemIdRef, range)

const { createPlan, updatePlan, deletePlan } = usePlanningMutations()

const eventModalOpen = ref(false)
const modalMode = ref<'view' | 'edit' | 'create'>('create')
const modalDraft = ref<PlanningEventDraft>({
  id: '',
  subitemId: '',
  startDate: '',
  startTime: '',
  endDate: '',
  endTime: ''
})
const apiError = ref('')

let dragEnd = ''
let dragEndDate = ''
let dragEndTime = ''

const splitDays = ref<CalendarSplit[]>([])

const calendarView = computed<CalendarView>(() => ({
  timeframe: planningStore.view.timeframe,
  type: planningStore.view.timeframe
}))

const cellsInteractive = computed(
  () => planningStore.view.timeframe !== 'month' && selectedItemId.value !== ''
)

const onViewChanged = (event: Record<string, unknown>) => {
  const start = localTimeToUtc(String(event.startDate ?? event.firstCellDate ?? ''))
  const end = localTimeToUtc(String(event.endDate ?? event.lastCellDate ?? ''))
  const timeframe = (event.view as 'month' | 'week' | 'day') ?? planningStore.view.timeframe
  planningStore.setView({ timeframe, start, end })
  range.value = { start, end }
}

const onCellDragged = (event: Record<string, unknown>) => {
  const end = event.end as Date | string
  dragEnd = end instanceof Date ? end.toString() : String(end)
  dragEndDate = formatAsDate(dragEnd)
  dragEndTime = formatAsTime(dragEnd)
}

const openCreateModal = (start: Date | string, endDate = '', endTime = '') => {
  apiError.value = ''
  modalMode.value = 'create'
  modalDraft.value = {
    id: '',
    subitemId: '',
    startDate: formatAsDate(start),
    startTime: formatAsTime(start),
    endDate,
    endTime
  }
  eventModalOpen.value = true
}

const onCellClicked = (event: Record<string, unknown>) => {
  if (!cellsInteractive.value) return
  const raw = (event.date ?? event.start) as Date | string
  let start = raw instanceof Date ? raw : new Date(String(raw))
  if (start < new Date()) {
    start = new Date(Date.now() + 5 * 60_000)
  }
  openCreateModal(start, dragEndDate, dragEndTime)
  dragEnd = ''
  dragEndDate = ''
  dragEndTime = ''
}

const onEventClicked = (event: CalendarEvent) => {
  modalMode.value = 'edit'
  apiError.value = ''
  modalDraft.value = {
    id: event.id,
    subitemId: (event as CalendarEvent & { subitemId?: string }).subitemId ?? '',
    startDate: formatAsDate(event.start),
    startTime: formatAsTime(event.start),
    endDate: formatAsDate(event.end),
    endTime: formatAsTime(event.end)
  }
  eventModalOpen.value = true
}

const onModalClose = () => {
  eventModalOpen.value = false
  apiError.value = ''
}

const draftToRange = (draft: PlanningEventDraft) => ({
  start: new Date(`${draft.startDate}T${draft.startTime}`),
  end: new Date(`${draft.endDate}T${draft.endTime}`)
})

const onModalSubmit = (draft: PlanningEventDraft) => {
  const { start, end } = draftToRange(draft)
  if (modalMode.value === 'create') {
    createPlan.mutate(
      {
        body: {
          item_type: selectedType.value,
          item_id: selectedItemId.value,
          subitem_id: draft.subitemId,
          start: start.toISOString(),
          end: end.toISOString()
        }
      },
      {
        onSuccess: () => {
          eventModalOpen.value = false
        },
        onError: (err: unknown) => {
          apiError.value = describeApiError(err, i18n, 'planning')
        }
      }
    )
  } else if (modalMode.value === 'edit') {
    updatePlan.mutate(
      {
        path: {
          plan_id: draft.id,
          start: encodeURIComponent(start.toISOString()),
          end: encodeURIComponent(end.toISOString())
        }
      },
      {
        onSuccess: () => {
          eventModalOpen.value = false
        },
        onError: (err: unknown) => {
          apiError.value = describeApiError(err, i18n, 'planning')
        }
      }
    )
  }
}

const onModalDelete = (draft: PlanningEventDraft) => {
  if (!draft.id) return
  deletePlan.mutate(
    { path: { plan_id: draft.id } },
    {
      onSuccess: () => {
        eventModalOpen.value = false
      },
      onError: (err: unknown) => {
        apiError.value = (err as { message?: string })?.message ?? ''
      }
    }
  )
}

watch(selectedType, () => {
  selectedItemId.value = ''
})

onUnmounted(() => {
  planningStore.$reset()
})
</script>

<template>
  <div class="calendar-container">
    <div class="grid grid-cols-2 gap-4 mb-4 px-2">
      <div>
        <Label for="bookable-type">
          {{ t('components.bookings.item.new-planning.bookable-type') }}
        </Label>
        <Select
          :model-value="selectedType"
          @update:model-value="(v) => (selectedType = String(v ?? ''))"
        >
          <SelectTrigger id="bookable-type" size="default" class="w-full">
            <SelectValue :placeholder="t('components.bookings.item.new-planning.bookable-type')" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="type in types" :key="type" :value="type">
              {{ type }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label for="bookable-item">
          {{ t('components.bookings.item.new-planning.bookable-item') }}
        </Label>
        <Select
          :model-value="selectedItemId"
          :disabled="!selectedType"
          @update:model-value="(v) => (selectedItemId = String(v ?? ''))"
        >
          <SelectTrigger id="bookable-item" size="default" class="w-full">
            <SelectValue :placeholder="t('components.bookings.item.new-planning.bookable-item')" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="item in items" :key="item.id" :value="item.id">
              {{ item.name }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
    <div class="calendar-row-container">
      <BookingCalendar
        :events="events"
        :split-days="splitDays"
        :view="calendarView"
        :snap-to-time="15"
        @view-changed="onViewChanged"
        @event-clicked="onEventClicked"
        @cell-clicked="onCellClicked"
        @cell-dragged="onCellDragged"
      />
    </div>
    <PlanningEventModal
      :open="eventModalOpen"
      :mode="modalMode"
      :draft="modalDraft"
      :subitems="subitems"
      :submitting="createPlan.isPending.value || updatePlan.isPending.value"
      :deleting="deletePlan.isPending.value"
      :api-error="apiError"
      @close="onModalClose"
      @submit="onModalSubmit"
      @delete="onModalDelete"
    />
  </div>
</template>

<style scoped>
.calendar-container {
  height: 100vh;
  width: 95%;
  padding: 1rem;
}
.calendar-row-container {
  height: calc(100vh - 15rem);
}
</style>
