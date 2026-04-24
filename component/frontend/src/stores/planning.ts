import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { BookingTimeframe } from '@/lib/booking/constants'

export interface PlanningView {
  timeframe: BookingTimeframe
  start: string
  end: string
}

export type PlanningModalMode = 'view' | 'edit' | 'create'

export interface PlanningEventDraft {
  id: string
  subitemId: string
  startDate: string
  startTime: string
  endDate: string
  endTime: string
}

export interface PlanningEventModalState {
  open: boolean
  mode: PlanningModalMode
  draft: PlanningEventDraft
}

const emptyDraft = (): PlanningEventDraft => ({
  id: '',
  subitemId: '',
  startDate: '',
  startTime: '',
  endDate: '',
  endTime: ''
})

export const usePlanningStore = defineStore('planning', () => {
  const selectedReservableType = ref<string>('')
  const selectedReservableItemId = ref<string>('')
  const selectedSubitemId = ref<string>('')

  const view = ref<PlanningView>({
    timeframe: 'week',
    start: '',
    end: ''
  })

  const eventModal = ref<PlanningEventModalState>({
    open: false,
    mode: 'view',
    draft: emptyDraft()
  })

  const setReservableType = (type: string) => {
    selectedReservableType.value = type
    selectedReservableItemId.value = ''
    selectedSubitemId.value = ''
  }

  const setReservableItem = (id: string) => {
    selectedReservableItemId.value = id
  }

  const setView = (next: Partial<PlanningView>) => {
    view.value = { ...view.value, ...next }
  }

  const openEventModal = (mode: PlanningModalMode, draft: Partial<PlanningEventDraft> = {}) => {
    eventModal.value = {
      open: true,
      mode,
      draft: { ...emptyDraft(), ...draft }
    }
  }

  const closeEventModal = () => {
    eventModal.value = { open: false, mode: 'view', draft: emptyDraft() }
  }

  const $reset = () => {
    selectedReservableType.value = ''
    selectedReservableItemId.value = ''
    selectedSubitemId.value = ''
    view.value = { timeframe: 'week', start: '', end: '' }
    closeEventModal()
  }

  return {
    selectedReservableType,
    selectedReservableItemId,
    selectedSubitemId,
    view,
    eventModal,
    setReservableType,
    setReservableItem,
    setView,
    openEventModal,
    closeEventModal,
    $reset
  }
})
