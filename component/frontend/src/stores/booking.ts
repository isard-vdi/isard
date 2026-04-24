import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { BookingItemType, BookingTimeframe, BookingViewType } from '@/lib/booking/constants'

export interface BookingView {
  timeframe: BookingTimeframe
  viewType: BookingViewType
  start: string
  end: string
}

export type BookingModalMode = 'view' | 'edit' | 'create'

export interface BookingEventDraft {
  id: string
  title: string
  startDate: string
  startTime: string
  endDate: string
  endTime: string
}

export interface BookingEventModalState {
  open: boolean
  mode: BookingModalMode
  draft: BookingEventDraft
}

const emptyDraft = (): BookingEventDraft => ({
  id: '',
  title: '',
  startDate: '',
  startTime: '',
  endDate: '',
  endTime: ''
})

export interface BookingPriorityState {
  forbidTime: number
  maxTime: number
  maxItems: number
}

export const useBookingStore = defineStore('booking', () => {
  const itemId = ref<string | null>(null)
  const itemType = ref<BookingItemType>('all')
  const itemName = ref<string>('')

  const view = ref<BookingView>({
    timeframe: 'week',
    viewType: 'summary',
    start: '',
    end: ''
  })

  const eventModal = ref<BookingEventModalState>({
    open: false,
    mode: 'view',
    draft: emptyDraft()
  })

  const setItem = (id: string | null, type: BookingItemType, name = '') => {
    itemId.value = id
    itemType.value = type
    itemName.value = name
  }

  const setView = (next: Partial<BookingView>) => {
    view.value = { ...view.value, ...next }
  }

  const openEventModal = (mode: BookingModalMode, draft: Partial<BookingEventDraft> = {}) => {
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
    itemId.value = null
    itemType.value = 'all'
    itemName.value = ''
    view.value = { timeframe: 'week', viewType: 'summary', start: '', end: '' }
    closeEventModal()
  }

  return {
    itemId,
    itemType,
    itemName,
    view,
    eventModal,
    setItem,
    setView,
    openEventModal,
    closeEventModal,
    $reset
  }
})
