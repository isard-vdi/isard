<script setup lang="ts">
import {
  computed,
  nextTick,
  onMounted,
  readonly,
  ref,
  shallowRef,
  toValue,
  reactive,
  watch,
  watchEffect
} from 'vue'

import { useRoute, useRouter, RouterLink } from 'vue-router'
import {
  useLocalStorage as vueuseLocalStorage,
  refDebounced,
  useElementSize,
  useEventListener,
  useWindowSize,
  useWindowScroll
} from '@vueuse/core'
import { useCookies as vueuseCookies } from '@vueuse/integrations/useCookies'
import { useI18n } from 'vue-i18n'
import { useQuery, useQueryClient, useMutation } from '@tanstack/vue-query'
import { useForm } from '@tanstack/vue-form'
import { useWindowVirtualizer, type VirtualItem } from '@tanstack/vue-virtual'

import {
  getUserDesktopsOptions,
  getUserDesktopsQueryKey,
  getUserConfigOptions,
  getDesktopNetworksOptions,
  updateStatusDesktopMutation,
  deleteDesktopMutation,
  recreateDesktopMutation,
  getRecycleBinDefaultDeleteConfigOptions,
  getRecycleBinCutoffTimeOptions,
  updateDesktopBastionAuthorizedKeysMutation,
  stopDesktopsMutation,
  getMaxBookingDateOptions,
  editDesktopMutation,
  createBookingEventMutation,
  startDesktopMutation,
  stopDesktopMutation,
  checkQuotaNewDesktopOptions,
  checkQuotaNewTemplateOptions,
  checkStoragePoolCreationAvailabilityOptions,
  getDesktopDetailsOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import {
  startDesktop,
  stopDesktop,
  stopDesktops,
  getDesktopNetworks,
  deleteDesktop,
  updateDesktopBastionAuthorizedKeys,
  getDesktopViewerByType as getDesktopViewer,
  type GetDesktopViewerByTypeData as GetDesktopViewerData,
  type DesktopNetwork,
  type GetDesktopNetworksData,
  DesktopStatusEnum,
  type ApiSchemasDomainsDesktopsUserDesktop as UserDesktop,
  getMaxBookingDate,
  type ErrorResponse,
  getBookingReservablesAvailable as getBookingReservablesAvailable,
  getUserNotificationTriggerDisplay,
  NotificationTriggerEnum,
  NotificationDisplayEnum
} from '@/gen/oas/apiv4/'

import { cn } from '@/lib/utils'
import { getEndTimeIntervals } from '@/lib/booking/end-time-intervals'
import { QUOTA_STALE_TIME } from '@/lib/constants'
import { sessionTokenName } from '@/lib/auth'
import { withOptimisticItemStatus, withOptimisticItemRemoval } from '@/lib/optimistic'
import { describeApiError } from '@/lib/api-errors'
import { resolveDesktopKind } from '@/lib/desktops'
import { useNotificationModalStore } from '@/stores/notification-modal'

import { SinglePageLayout } from '@/layouts/single-page'

import {
  DomainInfoModal,
  DirectViewerModal,
  DesktopBastionInfoModal,
  DesktopNetworksModal
} from '@/components/desktops'
import { DesktopStorageModal } from '@/components/desktop-card/desktop-storage-modal'

import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { BadgeMini } from '@/components/badge/mini'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import { Checkbox } from '@/components/ui/checkbox'
import { DropdownButton } from '@/components/dropdown-button'
import {
  DesktopCard,
  DesktopCardSkeleton,
  DesktopCardNetworksOverlay,
  type CardSize
} from '@/components/desktop-card'
import { DesktopsDataTable } from '@/components/desktops-data-table'
import { EmptyState } from '@/components/page'
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet
} from '@/components/ui/field'
import { Icon, CopyIcon } from '@/components/icon'
import { InputField } from '@/components/input-field'
import { Label } from '@/components/ui/label'
import { AlertModal, Modal, QuotaExceededModal } from '@/components/modal'
import BookingChangeAndStartModal from '@/components/booking/BookingChangeAndStartModal.vue'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { RecreateDesktopConfirmationModal } from '@/components/recreate-desktop-confirmation-modal'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Toggle } from '@/components/ui/toggle'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ViewerSelect } from '@/components/viewer-select'

import { useFetchAndOpenViewer } from '@/composables/useFetchAndOpenViewer'
import { useFastScroll } from '@/composables/useFastScroll'
import { useSearchShortcuts } from '@/composables/useSearchShortcuts'
import { Kbd } from '@/components/kbd'

const { t, d, te } = useI18n()
const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const notificationModalStore = useNotificationModalStore()

const { mutate: fetchAndOpenViewer, preferedViewers } = useFetchAndOpenViewer()

const {
  isPending: desktopsIsPending,
  isError: desktopsIsError,
  error: desktopsError,
  data: desktops
} = useQuery(getUserDesktopsOptions())

const routeDesktop = computed(() => {
  if (
    !route.params.desktopId ||
    !desktops.value?.desktops ||
    desktops.value.desktops.length === 0
  ) {
    return null
  }

  return desktops.value.desktops.find((d) => d.id === route.params.desktopId) || null
})

const {
  isPending: userConfigIsPending,
  isError: userConfigIsError,
  error: userConfigError,
  data: userConfig
} = useQuery(getUserConfigOptions())

const {
  isPending: recycleBinDefaultDeleteIsPending,
  isError: recycleBinDefaultDeleteIsError,
  error: recycleBinDefaultDeleteError,
  data: recycleBinDefaultDelete
} = useQuery(getRecycleBinDefaultDeleteConfigOptions())

const {
  isPending: recycleBinCutoffTimeIsPending,
  isError: recycleBinCutoffTimeIsError,
  error: recycleBinCutoffTimeError,
  data: recycleBinCutoffTime
} = useQuery(getRecycleBinCutoffTimeOptions())

const quotaExceededModalData = ref<{
  title: string
  description: string
  cancelLabel: string
} | null>(null)

const QUOTA_EXCEEDED_MODAL_KEYS: Record<string, string> = {
  desktop_start_user_quota_exceeded: 'start-quota-exceeded-modal',
  desktop_start_group_limit_exceeded: 'start-quota-exceeded-modal',
  desktop_start_category_limit_exceeded: 'start-quota-exceeded-modal',
  desktop_start_memory_quota_exceeded: 'start-memory-quota-exceeded-modal',
  desktop_start_group_memory_limit_exceeded: 'start-memory-quota-exceeded-modal',
  desktop_start_category_memory_limit_exceeded: 'start-memory-quota-exceeded-modal',
  desktop_start_vcpu_quota_exceeded: 'start-vcpu-quota-exceeded-modal',
  desktop_start_group_vcpu_limit_exceeded: 'start-vcpu-quota-exceeded-modal',
  desktop_start_category_vcpu_limit_exceeded: 'start-vcpu-quota-exceeded-modal',
  total_size_quota_exceeded: 'start-disk-quota-exceeded-modal',
  group_total_size_limit_exceeded: 'start-disk-quota-exceeded-modal',
  category_total_size_limit_exceeded: 'start-disk-quota-exceeded-modal'
}

const showStartStorageUnavailableModal = ref(false)

const desktopsKey = getUserDesktopsQueryKey()

const {
  mutate: desktopStart,
  mutateAsync: desktopStartAsync,
  isPending: desktopStartIsPending,
  isError: desktopStartIsError,
  error: desktopStartError
} = useMutation(
  withOptimisticItemStatus<{ path: { desktop_id: string } }, UserDesktop, 'desktops'>({
    queryClient,
    queryKey: desktopsKey,
    listKey: 'desktops',
    extractItemId: (vars) => vars.path.desktop_id,
    nextStatus: DesktopStatusEnum.STARTING,
    // Mirror DesktopEvents.desktop_start: only Stopped/Failed accept a start.
    // Skipping the optimistic flip on already-Started rows prevents a flicker
    // (Started → Starting → Started) from re-firing the engine path and
    // regenerating the SPICE password live.
    nextStatusGuard: (current) =>
      current === DesktopStatusEnum.STOPPED || current === DesktopStatusEnum.FAILED,
    baseMutation: startDesktopMutation(),
    onError: (error) => {
      const err = error as ErrorResponse
      const modalKey = QUOTA_EXCEEDED_MODAL_KEYS[err.description_code]
      if (modalKey) {
        quotaExceededModalData.value = {
          title: t(`components.desktops.${modalKey}.title`),
          description: t(`components.desktops.${modalKey}.description`),
          cancelLabel: t(`components.desktops.${modalKey}.cancel`)
        }
      } else if (err.description_code === 'no_storage_pool_available') {
        showStartStorageUnavailableModal.value = true
      }
    },
    onSuccess: async () => {
      try {
        const { data } = await getUserNotificationTriggerDisplay({
          path: {
            trigger: NotificationTriggerEnum.START_DESKTOP,
            display: NotificationDisplayEnum.MODAL
          }
        })
        const items = data?.notifications
        if (items && items.length > 0) {
          notificationModalStore.show(items)
        }
      } catch (e) {
        console.error('Failed to fetch start_desktop notifications', e)
      }
    }
  })
)

const {
  mutate: desktopStop,
  mutateAsync: desktopStopAsync,
  isPending: desktopStopIsPending,
  isError: desktopStopIsError,
  error: desktopStopError
} = useMutation(
  withOptimisticItemStatus<{ path: { desktop_id: string } }, UserDesktop, 'desktops'>({
    queryClient,
    queryKey: desktopsKey,
    listKey: 'desktops',
    extractItemId: (vars) => vars.path.desktop_id,
    nextStatus: DesktopStatusEnum.STOPPING,
    nextStatusGuard: (current) =>
      current === DesktopStatusEnum.STARTED ||
      current === DesktopStatusEnum.WAITING_IP ||
      current === DesktopStatusEnum.SHUTTING_DOWN ||
      current === DesktopStatusEnum.PAUSED ||
      current === DesktopStatusEnum.SUSPENDED,
    baseMutation: stopDesktopMutation()
  })
)

const {
  mutate: submitDesktopUpdateStatus,
  mutateAsync: submitDesktopUpdateStatusAsync,
  isPending: submitDesktopUpdateStatusIsPending,
  isError: submitDesktopUpdateStatusIsError,
  error: submitDesktopUpdateStatusError
} = useMutation(
  withOptimisticItemStatus<{ path: { desktop_id: string } }, UserDesktop, 'desktops'>({
    queryClient,
    queryKey: desktopsKey,
    listKey: 'desktops',
    extractItemId: (vars) => vars.path.desktop_id,
    nextStatus: DesktopStatusEnum.UPDATING,
    baseMutation: updateStatusDesktopMutation()
  })
)

// --------------------------------------------------
// --------------------------------------------------

const showStopAllDesktopsModal = ref(false)
const stopAllDesktopsForce = ref(false)
const {
  mutate: stopAllDesktops,
  isPending: stopAllDesktopsIsPending,
  isError: stopAllDesktopsIsError,
  error: stopAllDesktopsError
} = useMutation({
  ...stopDesktopsMutation(),
  onSuccess: () => {
    showStopAllDesktopsModal.value = false
    stopAllDesktopsForce.value = false
  }
})

// --------------------------------------------------

const networksModalData = ref<{
  id: string
  name: string
  ip?: string | null
  status?: string
} | null>(null)

// --------------------------------------------------

const showDesktopInfoModal = ref(false)

const storageModalDesktop = ref<UserDesktop | null>(null)
const {
  mutate: fetchDesktopDetails,
  isPending: fetchDesktopDetailsIsPending,
  isError: fetchDesktopDetailsIsError,
  error: fetchDesktopDetailsError,
  data: desktopDetails,
  variables: desktopDetailsDesktopId,
  reset: resetDesktopDetails
} = useMutation({
  mutationFn: (desktopId: string) =>
    queryClient.fetchQuery(
      getDesktopDetailsOptions({
        path: {
          desktop_id: desktopId
        },
        throwOnError: true
      })
    )
})

const openDesktopInfoModal = async (desktopId: string) => {
  fetchDesktopDetails(desktopId)
  showDesktopInfoModal.value = true
}

const desktopDetailsKind = computed(() => {
  const id = desktopDetailsDesktopId.value
  if (!id) return undefined
  const desktop = desktops.value?.desktops.find((d) => d.id === id)
  if (!desktop) return undefined
  return resolveDesktopKind(desktop)
})

// --------------------------------------------------

const deleteModalDesktopData = ref<{
  id: string
  name: string
} | null>(null)
const deleteModalRecicleBinChecked = ref(recycleBinDefaultDelete.value)

const deleteDesktopErrorMessage = ref<string | null>(null)

const {
  mutate: deleteDesktopMutate,
  mutateAsync: deleteDesktopAsync,
  isPending: deleteDesktopIsPending
} = useMutation(
  withOptimisticItemRemoval<{ path: { desktop_id: string } }, UserDesktop, 'desktops'>({
    queryClient,
    queryKey: desktopsKey,
    listKey: 'desktops',
    extractItemId: (vars) => vars.path.desktop_id,
    baseMutation: deleteDesktopMutation(),
    onSuccess: () => {
      closeDeleteModal()
    },
    onError: (error) => {
      deleteDesktopErrorMessage.value = describeApiError(error, { t, te }, 'delete-desktop')
    }
  })
)

const closeDeleteModal = () => {
  deleteModalRecicleBinChecked.value = recycleBinDefaultDelete.value
  deleteModalDesktopData.value = null
  deleteDesktopErrorMessage.value = null
}

// --------------------------------------------------

const recreateDesktopModalDesktopData = ref<{
  id: string
  name: string
} | null>(null)

// --------------------------------------------------

interface BastionModalData {
  desktopId: string
  desktopName: string
}
const bastionModalData = ref<BastionModalData | null>(null)

// --------------------------------------------------

const anyDesktopStarted = computed(() => {
  return !!desktops.value?.desktops.some((desktop) =>
    [
      DesktopStatusEnum.STARTING,
      DesktopStatusEnum.STARTED,
      DesktopStatusEnum.SHUTTING_DOWN,
      DesktopStatusEnum.STOPPING,
      DesktopStatusEnum.WAITING_IP
    ].includes(desktop.status)
  )
})

// --------------------------------------------------

const showDirectLink = (desktopId: string) => {
  directLinkDesktopId.value = desktopId
}

const directLinkDesktopId = ref<string | null>(null)

// --------------------------------------------------

const copyText = (text: string) => {
  navigator.clipboard.writeText(text).catch((err) => {
    console.error('Could not copy text: ', err)
  })
}

// --------------------------------------------------

interface DesktopFilters {
  search: string
  kind: {
    persistent: boolean
    volatile: boolean
    deployment: boolean
  }
  status: 'all' | 'started' | 'stopped'
}

const defaultDesktopFilters: DesktopFilters = {
  search: '',
  kind: {
    persistent: false,
    volatile: false,
    deployment: false
  },
  status: 'all'
}

const desktopFilters = ref<DesktopFilters>(JSON.parse(JSON.stringify(defaultDesktopFilters)))
const desktopFiltersKindAll = computed({
  get: () => {
    return (
      !desktopFilters.value.kind.persistent &&
      !desktopFilters.value.kind.volatile &&
      !desktopFilters.value.kind.deployment
    )
  },
  set: (value: boolean) => {
    if (value) {
      desktopFilters.value.kind.persistent = false
      desktopFilters.value.kind.volatile = false
      desktopFilters.value.kind.deployment = false
    }
  }
})

const areDesktopFiltersActive = computed(() => {
  return JSON.stringify(desktopFilters.value) !== JSON.stringify(defaultDesktopFilters)
})

// Search has its own always-visible input; only the ones the panel hides count.
const activeDesktopFilterCount = computed(() => {
  const kinds = Object.values(desktopFilters.value.kind).filter(Boolean).length
  return kinds + (desktopFilters.value.status === 'all' ? 0 : 1)
})

const desktopFiltersToggleLabel = computed(() =>
  activeDesktopFilterCount.value
    ? t('views.desktops.filters.toggle-active', { count: activeDesktopFilterCount.value })
    : t('views.desktops.filters.toggle')
)

// Nothing to search or filter until the account holds a desktop.
const isFirstRun = computed(
  () => !desktopsIsPending.value && (desktops.value?.desktops.length ?? 0) === 0
)

const clearDesktopFilters = () => {
  desktopFilters.value = JSON.parse(JSON.stringify(defaultDesktopFilters))
}

// The input keeps updating on every keystroke; only the filtering waits, so the
// grid is not rebuilt (and the query re-run over every desktop) mid-word.
const debouncedDesktopSearch = refDebounced(
  computed(() => desktopFilters.value.search.trim().toLowerCase()),
  150
)

const RUNNING_DESKTOP_STATUSES: DesktopStatusEnum[] = [
  DesktopStatusEnum.STARTING,
  DesktopStatusEnum.STARTED,
  DesktopStatusEnum.SHUTTING_DOWN,
  DesktopStatusEnum.WAITING_IP
]

const filteredDesktops = computed(() => {
  return (
    desktops.value?.desktops.filter((desktop) => {
      return isDesktopVisible(desktop)
    }) || []
  )
})

const isDesktopVisible = (desktop: UserDesktop) => {
  // Search filter
  const search = debouncedDesktopSearch.value
  const matchesSearch =
    search === '' ||
    desktop.name.toLowerCase().includes(search) ||
    !!desktop.description?.toLowerCase().includes(search)

  // Kind filter
  const matchesKind =
    (!desktopFilters.value.kind.persistent &&
      !desktopFilters.value.kind.volatile &&
      !desktopFilters.value.kind.deployment) ||
    (desktopFilters.value.kind.persistent && desktop.type === 'persistent' && !desktop.tag) ||
    (desktopFilters.value.kind.volatile && desktop.type === 'nonpersistent') ||
    (desktopFilters.value.kind.deployment && desktop.tag)

  // Status filter
  const matchesStatus =
    desktopFilters.value.status === 'all' ||
    (desktopFilters.value.status === 'started' &&
      RUNNING_DESKTOP_STATUSES.includes(desktop.status)) ||
    (desktopFilters.value.status === 'stopped' &&
      !RUNNING_DESKTOP_STATUSES.includes(desktop.status))

  // ----------------------------------------------------
  return matchesSearch && matchesKind && matchesStatus
}

// --------------------------------------------------

const {
  mutate: fetchMaxBookingDate,
  mutateAsync: fetchMaxBookingDateAsync,
  data: maxBookingDate,
  isPending: fetchMaxBookingDateIsPending,
  isError: fetchMaxBookingDateIsError,
  error: fetchMaxBookingDateError
} = useMutation({
  mutationFn: async (desktopId: string) => {
    const { data } = await getMaxBookingDate({
      path: {
        desktop_id: desktopId
      },
      throwOnError: true
    })
    return data
  },
  onSuccess(data, variables, onMutateResult, context) {
    const desktop = desktops.value?.desktops.find((d) => d.id === variables)!

    startNowModalDesktopData.value = {
      id: desktop.id,
      name: desktop.name,
      currentGpu: desktop.reservables?.vgpus?.[0] || 'N/A'
    }
  },
  onError(error: ErrorResponse, variables, onMutateResult, context) {
    const desktop = desktops.value?.desktops.find((d) => d.id === variables)!

    switch (error.description_code) {
      case 'not_enough_advanced_time':
        notEnoughAdvancedTimeModalDesktopData.value = {
          id: desktop.id,
          name: desktop.name,
          currentGpu: desktop.reservables?.vgpus?.[0] || 'N/A'
        }
        break
      case 'current_plan_doesnt_match':
        unavailableStartNowModalDesktopData.value = {
          id: desktop.id,
          name: desktop.name,
          currentGpu: desktop.reservables?.vgpus?.[0] || 'N/A',
          currentGpus: desktop.reservables?.vgpus ?? []
        }
        break
      // TODO: handle other error cases
    }
  }
})

const {
  mutate: getAvailableReservables,
  data: availableReservables,
  isPending: getAvailableReservablesIsPending,
  isError: getAvailableReservablesIsError,
  error: getAvailableReservablesError
} = useMutation({
  mutationFn: async () => {
    const { data } = await getBookingReservablesAvailable({
      throwOnError: true
    })
    return data
  }
})

const notEnoughAdvancedTimeModalDesktopData = ref<{
  id: string
  name: string
  currentGpu: string
} | null>(null)

const startNowModalDesktopData = ref<{
  id: string
  name: string
  currentGpu: string
} | null>(null)

const unavailableStartNowModalDesktopData = ref<{
  id: string
  name: string
  currentGpu: string
  currentGpus: string[]
} | null>(null)

const changeAndStartModalData = ref<{
  id: string
  name: string
  currentGpu: string
  currentGpus: string[]
} | null>(null)

const {
  mutate: editDesktop,
  mutateAsync: editDesktopAsync,
  isPending: editDesktopIsPending,
  isError: editDesktopIsError,
  error: editDesktopError
} = useMutation(editDesktopMutation())

const {
  mutate: createBookingEvent,
  mutateAsync: createBookingEventAsync,
  isPending: createBookingEventIsPending,
  isError: createBookingEventIsError,
  error: createBookingEventError
} = useMutation(createBookingEventMutation())

const changeAndStartError = ref<string | null>(null)

const onChangeAndStartSubmit = async ({
  desktopId,
  profileIds,
  endTime
}: {
  desktopId: string
  profileIds: string[]
  endTime: string
}) => {
  changeAndStartError.value = null
  try {
    await editDesktopAsync({
      path: { desktop_id: desktopId },
      body: { reservables: { vgpus: profileIds } }
    })

    await createBookingEventAsync({
      body: {
        end: new Date(endTime).toISOString(),
        item_id: desktopId,
        start: new Date().toISOString(),
        now: true,
        item_type: 'desktop'
      }
    })

    desktopStart({ path: { desktop_id: desktopId } })
    closeChangeAndStartModal()
  } catch (error) {
    changeAndStartError.value = (error as ErrorResponse | undefined)?.description_code ?? 'generic'
  }
}

const closeChangeAndStartModal = () => {
  changeAndStartModalData.value = null
  changeAndStartError.value = null
}

const startNowForm = useForm({
  defaultValues: {
    end_time: ''
  },
  onSubmit: async ({ value }) => {
    try {
      await createBookingEventAsync({
        body: {
          end: new Date(value.end_time).toISOString(),
          item_id: startNowModalDesktopData.value!.id,
          start: new Date().toISOString(),
          now: true,
          item_type: 'desktop'
        }
      })

      desktopStart({ path: { desktop_id: startNowModalDesktopData.value!.id } })
      closeStartNowModal()
    } catch (bookingError) {
      console.error('Error creating booking event:', bookingError)
    }
  }
})

const closeStartNowModal = () => {
  startNowModalDesktopData.value = null
  startNowForm.reset()
}

const maxBookingDateEndTimeIntervals = computed<Date[]>(() => {
  if (!maxBookingDate.value) {
    return []
  }

  const maxDate = new Date(maxBookingDate.value.max_booking_date)
  return getEndTimeIntervals(maxDate)
})

function isInvalid(field: { state: { meta: { isTouched: boolean; isValid: boolean } } }) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}
const dktp2 = computed(() => desktops.value?.desktops[2])

const showStorageUnavailableModal = ref(false)
const desktopCreationCheckIsPending = ref(false)

const goToNewDesktop = async () => {
  desktopCreationCheckIsPending.value = true
  try {
    await queryClient.fetchQuery({
      ...checkQuotaNewDesktopOptions(),
      staleTime: QUOTA_STALE_TIME
    })
  } catch {
    desktopCreationCheckIsPending.value = false
    quotaExceededModalData.value = {
      title: t('components.desktops.quota-exceeded-modal.title'),
      description: t('components.desktops.quota-exceeded-modal.description'),
      cancelLabel: t('components.desktops.quota-exceeded-modal.cancel')
    }
    return
  }
  try {
    await queryClient.fetchQuery({
      ...checkStoragePoolCreationAvailabilityOptions(),
      staleTime: QUOTA_STALE_TIME
    })
  } catch {
    desktopCreationCheckIsPending.value = false
    showStorageUnavailableModal.value = true
    return
  }
  desktopCreationCheckIsPending.value = false
  router.push({ name: 'new-desktop' })
}

const goToProfile = () => {
  router.push({ name: 'profile' })
}

const goToEditDesktop = (desktopId: string) => {
  router.push({ name: 'edit-desktop', params: { desktopId } })
}

const goToBookingDesktop = (desktopId: string) => {
  window.location.assign(`/booking/desktop/${desktopId}`)
}

const templateCreationCheckIsPending = ref(false)

const goToNewTemplate = async (desktopId: string) => {
  templateCreationCheckIsPending.value = true
  try {
    await queryClient.fetchQuery({
      ...checkQuotaNewTemplateOptions(),
      staleTime: QUOTA_STALE_TIME
    })
  } catch {
    templateCreationCheckIsPending.value = false
    quotaExceededModalData.value = {
      title: t('components.templates.quota-exceeded-modal.title'),
      description: t('components.templates.quota-exceeded-modal.description'),
      cancelLabel: t('components.templates.quota-exceeded-modal.cancel')
    }
    return
  }
  templateCreationCheckIsPending.value = false
  router.push({ name: 'new-template', params: { desktopId } })
}

const viewMode = ref<'cards' | 'table'>('cards')

const DESKTOP_SEARCH_INPUT_ID = 'desktops-search'

useSearchShortcuts(DESKTOP_SEARCH_INPUT_ID)

const DESKTOP_FILTERS_COOKIE_NAME = 'desktops_filters_state'
const DESKTOP_FILTERS_COOKIE_MAX_AGE = 60 * 60 * 24 * 7

const cookies = vueuseCookies([DESKTOP_FILTERS_COOKIE_NAME])

// useCookies auto-parses "true"/"false" to boolean, so check both types
const desktopFiltersCookie = cookies.get(DESKTOP_FILTERS_COOKIE_NAME)
const showDesktopFilters = ref(desktopFiltersCookie === true || desktopFiltersCookie === 'true')

watch(showDesktopFilters, (newValue) => {
  cookies.set(DESKTOP_FILTERS_COOKIE_NAME, String(newValue), {
    path: '/',
    maxAge: DESKTOP_FILTERS_COOKIE_MAX_AGE
  })
})

const { width: windowWidth, height: windowHeight } = useWindowSize()
const { y: windowScrollY } = useWindowScroll()

// Below `sm` the toolbar buttons drop their label, so a tooltip takes over
const isSmallScreen = computed(() => windowWidth.value < 640)

const cardSize = computed<CardSize>(() => {
  if (windowWidth.value < 1280) return 'md'
  return 'lg'
})

const cardGridMinWidth = computed(() => (cardSize.value === 'md' ? 250 : 412))
const cardGridRowHeight = computed(() => (cardSize.value === 'md' ? 280 : 310))

// Tailwind `gap-4`.
const CARD_GRID_GAP = 16

const cardGridRef = ref<HTMLElement | null>(null)
const { width: cardGridWidth } = useElementSize(cardGridRef)

const desktopToolbarRef = ref<HTMLElement | null>(null)
// Border box: the toolbar's padding is part of what covers the curtain.
const { height: desktopToolbarHeight } = useElementSize(desktopToolbarRef, undefined, {
  box: 'border-box'
})

// Mirrors what `repeat(auto-fill, minmax(min, 1fr))` would have resolved to.
const cardGridColumns = computed(() => {
  if (!cardGridWidth.value) return 1
  return Math.max(
    1,
    Math.floor((cardGridWidth.value + CARD_GRID_GAP) / (cardGridMinWidth.value + CARD_GRID_GAP))
  )
})

const cardGridRows = computed(() => {
  const rows: UserDesktop[][] = []
  for (let i = 0; i < filteredDesktops.value.length; i += cardGridColumns.value) {
    rows.push(filteredDesktops.value.slice(i, i + cardGridColumns.value))
  }
  return rows
})

// The grid starts partway down the document, so the virtualizer needs to know
// how much page precedes it. Remeasured on anything that reflows the toolbar
// above, but never on scroll — that would be the reflow-per-event we just left.
const cardGridOffsetTop = ref(0)
// Viewport-relative, so the fixed overlay does not cover the sidebar.
const cardGridOffsetLeft = ref(0)
const measureCardGridOffset = () => {
  const el = cardGridRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  cardGridOffsetTop.value = rect.top + window.scrollY
  cardGridOffsetLeft.value = rect.left
}

onMounted(measureCardGridOffset)
useEventListener('resize', measureCardGridOffset)
// Deliberately not watching the desktop count: more rows grow the grid
// downwards but never move its top, so remeasuring per keystroke only bought a
// forced reflow — and a costlier one the more cards the DOM held.
watch([showDesktopFilters, cardGridColumns, cardGridWidth, viewMode], () =>
  nextTick(measureCardGridOffset)
)

const cardGridVirtualizer = useWindowVirtualizer(
  computed(() => ({
    count: cardGridRows.value.length,
    estimateSize: () => cardGridRowHeight.value + CARD_GRID_GAP,
    overscan: 2,
    scrollMargin: cardGridOffsetTop.value
  }))
)

const { isFastScrolling } = useFastScroll()

// The toolbar is sticky on top of the curtain, so the curtain starts where the
// toolbar ends: anything higher is a first row cut in half. Then enough rows to
// fill the rest of the viewport, plus the one it is scrolled into.
const TOOLBAR_TOP = 64
const curtainTop = computed(() => TOOLBAR_TOP + desktopToolbarHeight.value)
const curtainRows = computed(
  () =>
    Math.ceil((windowHeight.value - curtainTop.value) / (cardGridRowHeight.value + CARD_GRID_GAP)) +
    1
)

// The rows the cards render from lag the scroll by a frame, and stop moving
// altogether once the curtain is up. Committing them straight from the scroll
// event costs ~18ms a card in the very flush that has to reveal the curtain,
// which is how the fling used to outrun it.
const cardVirtualRows = shallowRef<VirtualItem[]>([])
let commitScheduled = false

const commitVirtualRows = () => {
  cardVirtualRows.value = cardGridVirtualizer.value.getVirtualItems()
}

watchEffect(() => {
  cardGridVirtualizer.value.getVirtualItems()
  if (commitScheduled) return
  commitScheduled = true
  requestAnimationFrame(() => {
    commitScheduled = false
    if (!isFastScrolling.value) commitVirtualRows()
  })
})

// Back in one go with the curtain: same flush, so the rows are on screen the
// moment it lifts.
watch(isFastScrolling, (fast) => {
  if (!fast) commitVirtualRows()
})

// The curtain stands in for rows that are not built. Filter down to a handful
// of desktops and every row on screen is already there, so a fling has nothing
// to wait for and the curtain would be pure noise.
const missingCardRows = computed(() => {
  const built = new Set(cardVirtualRows.value.map((row) => row.index))
  return cardGridVirtualizer.value.getVirtualItems().some((row) => !built.has(row.index))
})
</script>

<template>
  <DirectViewerModal
    :open="directLinkDesktopId !== null"
    :desktop-id="directLinkDesktopId"
    @close="directLinkDesktopId = null"
  />

  <!-- Quota Exceeded Modal -->
  <QuotaExceededModal
    :open="quotaExceededModalData !== null"
    :title="quotaExceededModalData?.title ?? ''"
    :description="quotaExceededModalData?.description ?? ''"
    :cancel-label="quotaExceededModalData?.cancelLabel ?? ''"
    :cancel-to="route.name === 'single-desktop' ? { name: 'desktops' } : ''"
    @close="quotaExceededModalData = null"
  />

  <!-- Storage Unavailable Modal -->
  <AlertModal
    :open="showStorageUnavailableModal"
    level="danger"
    size="md"
    :title="t('components.desktops.storage-unavailable-modal.title')"
    :description="t('components.desktops.storage-unavailable-modal.description')"
    @close="showStorageUnavailableModal = false"
  >
    <template #footer>
      <Button hierarchy="primary" @click="showStorageUnavailableModal = false">{{
        t('components.desktops.storage-unavailable-modal.go-to-desktops')
      }}</Button>
    </template>
  </AlertModal>

  <!-- Start storage Unavailable Modal -->
  <AlertModal
    :open="showStartStorageUnavailableModal"
    level="danger"
    size="md"
    :title="t('components.desktops.start-storage-unavailable-modal.title')"
    :description="t('components.desktops.start-storage-unavailable-modal.description')"
    @close="showStartStorageUnavailableModal = false"
  >
    <template #footer>
      <Button hierarchy="primary" @click="showStartStorageUnavailableModal = false">{{
        t('components.desktops.start-storage-unavailable-modal.go-to-desktops')
      }}</Button>
    </template>
  </AlertModal>

  <!-- Delete modal -->
  <AlertModal
    :open="deleteModalDesktopData !== null"
    level="danger"
    size="lg"
    :title="
      t('components.delete-confirmation-modal.title', {
        kind: t('domains.with-article.desktops', 1),
        name: deleteModalDesktopData?.name
      })
    "
    @close="closeDeleteModal()"
  >
    <!-- TODO: Delete modal component -->
    <template #description>
      <Alert v-if="deleteDesktopErrorMessage" variant="destructive" class="mb-4">
        <AlertDescription>{{ deleteDesktopErrorMessage }}</AlertDescription>
      </Alert>
      <Label
        v-if="recycleBinCutoffTime?.recycle_bin_cutoff_time"
        class="w-fit flex flex-row items-start gap-2"
      >
        <Checkbox v-model="deleteModalRecicleBinChecked" class="m-0.5" />
        <div class="flex flex-col">
          <span>{{ t('components.delete-confirmation-modal.description.recycle-bin.title') }}</span>
          <span class="text-muted-foreground text-xs">{{
            t('components.delete-confirmation-modal.description.recycle-bin.subtitle', {
              hours: recycleBinCutoffTime?.recycle_bin_cutoff_time
            })
          }}</span>
        </div>
      </Label>
      <Label v-else class="w-fit flex flex-row items-start gap-0">{{
        t('components.delete-confirmation-modal.description.permanent.title')
      }}</Label>
    </template>
    <template #footer>
      <Button hierarchy="link-gray" @click="closeDeleteModal()">{{
        t('components.delete-confirmation-modal.cancel')
      }}</Button>

      <Button
        v-if="deleteModalDesktopData"
        hierarchy="destructive"
        :disabled="deleteDesktopIsPending"
        @click="
          deleteDesktopMutate({
            path: { desktop_id: deleteModalDesktopData.id },
            query: {
              permanent:
                recycleBinCutoffTime?.recycle_bin_cutoff_time === 0 || !deleteModalRecicleBinChecked
            }
          })
        "
      >
        <Icon
          v-if="deleteDesktopIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{
          recycleBinCutoffTime?.recycle_bin_cutoff_time === 0 || !deleteModalRecicleBinChecked
            ? t('components.delete-confirmation-modal.confirm.permanent')
            : t('components.delete-confirmation-modal.confirm.recycle-bin')
        }}
      </Button>
      <Skeleton v-else class="h-full w-32" />
    </template>
  </AlertModal>

  <DomainInfoModal
    :open="showDesktopInfoModal"
    :is-loading="fetchDesktopDetailsIsPending"
    :domain-id="desktopDetailsDesktopId"
    :name="desktopDetails?.name || ''"
    :description="desktopDetails?.description"
    :status="desktopDetails?.status"
    :ip="desktopDetails?.ip"
    :vcpu="desktopDetails?.vcpu"
    :ram="desktopDetails?.memory"
    :boot-order="desktopDetails?.boot_order.map((bo) => bo.name)"
    :disk-bus="desktopDetails?.disk_bus?.name"
    :vga="desktopDetails?.videos.map((vga) => vga.name)"
    :viewers="desktopDetails?.viewers"
    :isos="desktopDetails?.isos?.map((iso) => iso.name)"
    :floppies="desktopDetails?.floppies?.map((floppy) => floppy.name)"
    :reservables="desktopDetails?.reservables?.vgpus"
    :credentials="desktopDetails?.credentials"
    :kind="'desktop'"
    :template="desktopDetails?.template"
    :desktop-kind="desktopDetailsKind"
    @close="
      () => {
        showDesktopInfoModal = false
        resetDesktopDetails()
      }
    "
  />

  <!-- --- -->

  <DesktopNetworksModal
    v-if="networksModalData !== null"
    :open="networksModalData !== null"
    :desktop-id="networksModalData.id"
    :desktop-name="networksModalData.name"
    :desktop-ip="networksModalData.ip"
    :desktop-status="networksModalData.status"
    @close="networksModalData = null"
  />

  <DesktopBastionInfoModal
    v-if="bastionModalData !== null"
    :open="bastionModalData !== null"
    :desktop-id="bastionModalData.desktopId"
    :desktop-name="bastionModalData.desktopName"
    @close="bastionModalData = null"
  />

  <!-- Recreate modal -->

  <RecreateDesktopConfirmationModal
    v-if="recreateDesktopModalDesktopData !== null"
    :open="recreateDesktopModalDesktopData !== null"
    :desktop="recreateDesktopModalDesktopData"
    @close="recreateDesktopModalDesktopData = null"
  />

  <!-- Stop all modal -->
  <AlertModal
    :open="showStopAllDesktopsModal"
    level="warning"
    size="md"
    :title="t('components.stop-all-desktops-confirmation-modal.title')"
    :description="t('components.stop-all-desktops-confirmation-modal.description')"
    @close="showStopAllDesktopsModal = false"
  >
    <!-- TODO: Stop all modal component -->
    <template #description>
      <Label class="w-fit flex flex-row items-start gap-2 mt-2">
        <Checkbox v-model="stopAllDesktopsForce" class="m-0.5" />
        {{ t('components.stop-all-desktops-confirmation-modal.force') }}
      </Label>
    </template>

    <template #footer>
      <Button hierarchy="link-gray" @click="showStopAllDesktopsModal = false">{{
        t('components.stop-all-desktops-confirmation-modal.cancel')
      }}</Button>

      <Button
        hierarchy="destructive"
        :icon="stopAllDesktopsIsPending ? 'loading-02' : 'stop'"
        :icon-class="
          cn(stopAllDesktopsIsPending && 'motion-safe:animate-[spin_2s_linear_infinite]')
        "
        :disabled="stopAllDesktopsIsPending"
        @click="stopAllDesktops({ body: { force: stopAllDesktopsForce } })"
      >
        {{ t('components.stop-all-desktops-confirmation-modal.confirm') }}
      </Button>
    </template>
  </AlertModal>

  <!-- Not enough advanced time modal -->
  <AlertModal
    :open="notEnoughAdvancedTimeModalDesktopData !== null"
    level="warning"
    size="md"
    :title="t('components.not-enough-advanced-time-modal.title')"
    :description="t('components.not-enough-advanced-time-modal.description')"
    @close="notEnoughAdvancedTimeModalDesktopData = null"
  >
    <template #footer>
      <Button hierarchy="link-gray" @click="notEnoughAdvancedTimeModalDesktopData = null">{{
        t('components.not-enough-advanced-time-modal.cancel')
      }}</Button>

      <Button
        icon="calendar-plus-02"
        as="a"
        :href="`/booking/desktop/${notEnoughAdvancedTimeModalDesktopData?.id}`"
        target="_blank"
        >{{ t('components.not-enough-advanced-time-modal.book') }}</Button
      >
    </template>
  </AlertModal>

  <!-- Start now modal  -->
  <Modal
    :open="startNowModalDesktopData !== null"
    class="pt-4 min-w-120"
    :title="t('components.desktop-start-now-modal.title')"
    :description="t('components.desktop-start-now-modal.description')"
    @close="closeStartNowModal()"
  >
    <form
      id="start-now-form"
      class="flex flex-row items-center gap-2 w-full mt-2"
      @submit.prevent.stop="startNowForm.handleSubmit"
    >
      <FieldGroup class="gap-4">
        <startNowForm.Field name="end_time">
          <template #default="{ field }">
            <Field :data-invalid="isInvalid(field)">
              <FieldLabel :for="field.name">{{
                t('components.desktop-start-now-modal.select.label')
              }}</FieldLabel>

              <Select
                :id="field.name"
                :name="field.name"
                :aria-invalid="isInvalid(field)"
                class="w-full"
                :model-value="field.state.value"
                @update:model-value="field.handleChange($event?.toString() || '')"
              >
                <!-- TODO: better select component -->
                <SelectTrigger size="default" class="bg-base-white">
                  <SelectValue
                    :placeholder="t('components.desktop-start-now-modal.select.placeholder')"
                  />
                </SelectTrigger>
                <SelectContent class="left-0 right-0">
                  <SelectGroup>
                    <SelectItem
                      v-for="endTime in maxBookingDateEndTimeIntervals"
                      :key="endTime.toISOString()"
                      :value="endTime.toISOString()"
                    >
                      {{ d(endTime, { timeStyle: 'short' }) }}
                    </SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
          </template>
        </startNowForm.Field>
      </FieldGroup>
    </form>

    <template #footer>
      <Button hierarchy="link-gray" @click="startNowModalDesktopData = null">{{
        t('components.desktop-start-now-modal.cancel')
      }}</Button>

      <Button
        hierarchy="primary"
        :disabled="createBookingEventIsPending"
        type="submit"
        form="start-now-form"
      >
        <Icon
          v-if="createBookingEventIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        <Icon v-else name="play" stroke-color="currentColor" />
        {{ t('components.desktop-start-now-modal.confirm') }}
      </Button>
    </template>
  </Modal>

  <!-- TODO: custom modal component instead of AlertModal -->
  <!-- unavailable start now modal -->
  <Modal
    :open="unavailableStartNowModalDesktopData !== null"
    class="pt-4 min-w-120"
    :title="
      t('components.desktop-gpu-unavailable-modal.title', {
        'current-gpu': unavailableStartNowModalDesktopData?.currentGpu,
        name: unavailableStartNowModalDesktopData?.name
      })
    "
    :description="t('components.desktop-gpu-unavailable-modal.description')"
    @close="unavailableStartNowModalDesktopData = null"
  >
    <div class="flex flex-col gap-4 mt-4">
      <Alert class="flex flex-row gap-4 items-center justify-between">
        <div class="flex flex-col gap-2">
          <AlertTitle>{{
            t('components.desktop-gpu-unavailable-modal.change-and-start.title', {
              gpu: unavailableStartNowModalDesktopData?.currentGpu
            })
          }}</AlertTitle>
          <AlertDescription>{{
            t('components.desktop-gpu-unavailable-modal.change-and-start.subtitle')
          }}</AlertDescription>
        </div>
        <Button
          icon="switch-horizontal-01"
          @click="
            () => {
              getAvailableReservables()
              changeAndStartModalData = { ...unavailableStartNowModalDesktopData! }
              unavailableStartNowModalDesktopData = null
            }
          "
          >{{
            t('components.desktop-gpu-unavailable-modal.change-and-start.action-button')
          }}</Button
        >
      </Alert>

      <Alert class="flex flex-row gap-4 items-center justify-between">
        <div class="flex flex-col gap-2">
          <AlertTitle>{{
            t('components.desktop-gpu-unavailable-modal.book.title', {
              gpu: unavailableStartNowModalDesktopData?.currentGpu
            })
          }}</AlertTitle>
          <AlertDescription>{{
            t('components.desktop-gpu-unavailable-modal.book.subtitle')
          }}</AlertDescription>
        </div>
        <Button
          icon="calendar-plus-02"
          as="a"
          :href="`/booking/desktop/${unavailableStartNowModalDesktopData?.id}`"
          target="_blank"
          >{{ t('components.desktop-gpu-unavailable-modal.book.action-button') }}</Button
        >
      </Alert>
    </div>

    <template v-if="false" #footer>
      <Button hierarchy="link-gray" @click="closeRecreateDesktopModal()">{{
        t('components.desktop-gpu-unavailable-modal.cancel')
      }}</Button>

      <Button
        hierarchy="destructive"
        :disabled="recreateDesktopIsPending"
        @click="recreateDesktop({ path: { desktop_id: recreateDesktopModalDesktopData!.id } })"
      >
        <Icon
          v-if="recreateDesktopIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        {{ t('components.desktop-start-now-modal.confirm') }}
      </Button>
    </template>
  </Modal>

  <BookingChangeAndStartModal
    :open="changeAndStartModalData !== null"
    :desktop-id="changeAndStartModalData?.id ?? ''"
    :current-profile-ids="changeAndStartModalData?.currentGpus ?? []"
    :available-reservables="availableReservables"
    :is-loading-reservables="getAvailableReservablesIsPending"
    :submitting="editDesktopIsPending || createBookingEventIsPending"
    :submit-error="changeAndStartError"
    @close="closeChangeAndStartModal()"
    @submit="onChangeAndStartSubmit"
  />

  <main v-if="route.params.desktopId" class="flex w-full flex-1 items-center justify-center">
    <EmptyState
      :title="t(`views.desktops.${route.params.action}.title`, { kind: t('domains.desktops', 0) })"
      :description="
        t(`views.desktops.${route.params.action}.description`, { kind: t('domains.desktops', 0) })
      "
    >
      <DesktopCard
        v-if="routeDesktop"
        class="mt-6 text-start"
        size="lg"
        :desktop="routeDesktop"
        :preferred-viewer="preferedViewers[routeDesktop.id]"
        @desktop-start="desktopStart({ path: { desktop_id: routeDesktop.id } })"
        @desktop-stop="desktopStop({ path: { desktop_id: routeDesktop.id } })"
        @desktop-update-status="
          submitDesktopUpdateStatus({
            path: { desktop_id: routeDesktop.id }
          })
        "
        @desktop-fetch-booking="fetchMaxBookingDate(routeDesktop.id)"
        @open-viewer="(viewer) => fetchAndOpenViewer({ desktopId: routeDesktop.id, viewer })"
        @show-networks-modal="
          networksModalData = {
            id: routeDesktop.id,
            name: routeDesktop.name,
            ip: routeDesktop.ip,
            status: routeDesktop.status
          }
        "
        @show-info-modal="openDesktopInfoModal(routeDesktop.id)"
        @edit-desktop="goToEditDesktop(routeDesktop.id)"
        @show-delete-modal="
          deleteModalDesktopData = { id: routeDesktop.id, name: routeDesktop.name }
        "
        @show-bastion-modal="
          bastionModalData = { desktopId: routeDesktop.id, desktopName: routeDesktop.name }
        "
        @show-direct-link-modal="showDirectLink(routeDesktop.id)"
        @show-recreate-modal="
          recreateDesktopModalDesktopData = { id: routeDesktop.id, name: routeDesktop.name }
        "
        @create-template="goToNewTemplate(routeDesktop.id)"
        @book-desktop="goToBookingDesktop(routeDesktop.id)"
        @show-storage-modal="storageModalDesktop = routeDesktop"
      />

      <template #actions>
        <Button hierarchy="link-color" :as="RouterLink" :to="{ name: 'desktops' }">{{
          t('views.desktops.go-to-desktops')
        }}</Button>
        <Button
          :icon="desktopCreationCheckIsPending ? 'loading-02' : 'plus'"
          :icon-class="
            cn(desktopCreationCheckIsPending && 'motion-safe:animate-[spin_2s_linear_infinite]')
          "
          :disabled="desktopCreationCheckIsPending"
          size="lg"
          @click="goToNewDesktop"
        >
          {{ t('views.desktops.new-desktop') }}
        </Button>
      </template>
    </EmptyState>
  </main>

  <main v-else class="-mt-4 flex w-full flex-1 flex-col">
    <div
      v-if="!isFirstRun"
      ref="desktopToolbarRef"
      :class="
        cn(
          'sticky top-16 z-40 -mx-5 mb-1 flex flex-col gap-3 bg-base-background px-5 py-3 before:absolute before:inset-x-0 before:bottom-full before:h-8 before:bg-base-background',
          windowScrollY > 0 && 'shadow-lg'
        )
      "
    >
      <div class="flex flex-row w-full gap-2 sm:gap-4 items-start flex-wrap">
        <div class="flex flex-row gap-2 items-start flex-1 min-w-30 mr-auto">
          <InputField
            :id="DESKTOP_SEARCH_INPUT_ID"
            v-model="desktopFilters.search"
            :placeholder="t('views.desktops.filters.search.placeholder')"
            icon="search-lg"
            class="h-full w-full max-w-120 min-w-0"
          >
            <template #inline-end>
              <Kbd class="max-sm:hidden">/</Kbd>
            </template>
          </InputField>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  hierarchy="secondary-gray"
                  icon="filter-funnel-02"
                  :aria-label="desktopFiltersToggleLabel"
                  :class="
                    cn(
                      'relative shrink-0 max-sm:px-[10px]',
                      showDesktopFilters && 'bg-gray-warm-50'
                    )
                  "
                  @click="showDesktopFilters = !showDesktopFilters"
                >
                  <span class="max-sm:hidden">{{ t('views.desktops.filters.toggle') }}</span>
                  <!-- Stays visible with the panel collapsed, and on small screens
                       where the label is hidden. -->
                  <span
                    v-if="activeDesktopFilterCount"
                    aria-hidden="true"
                    class="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-brand-600 ring-2 ring-base-background"
                  />
                </Button>
              </TooltipTrigger>
              <TooltipContent
                v-if="isSmallScreen || activeDesktopFilterCount"
                :title="desktopFiltersToggleLabel"
                side="top"
              />
            </Tooltip>
          </TooltipProvider>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  hierarchy="secondary-gray"
                  :icon="viewMode === 'cards' ? 'rows-01' : 'grid-01'"
                  class="p-[10px] shrink-0"
                  @click="viewMode = viewMode === 'cards' ? 'table' : 'cards'"
                />
              </TooltipTrigger>
              <TooltipContent
                :title="
                  viewMode === 'cards'
                    ? t('views.desktops.view-mode.table')
                    : t('views.desktops.view-mode.cards')
                "
                side="top"
              />
            </Tooltip>
          </TooltipProvider>
        </div>

        <div class="flex flex-row gap-2 sm:gap-4 items-start shrink-0">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  hierarchy="destructive"
                  icon="stop"
                  :aria-label="t('views.desktops.stop-all')"
                  class="max-sm:px-[10px]"
                  :disabled="!anyDesktopStarted"
                  @click="showStopAllDesktopsModal = true"
                >
                  <span class="max-sm:hidden">{{ t('views.desktops.stop-all') }}</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent
                v-if="!anyDesktopStarted || isSmallScreen"
                :title="
                  anyDesktopStarted
                    ? t('views.desktops.stop-all')
                    : t('views.desktops.stop-all-tooltip.title')
                "
                side="top"
              />
            </Tooltip>
          </TooltipProvider>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  :icon="desktopCreationCheckIsPending ? 'loading-02' : 'plus'"
                  :icon-class="
                    cn(
                      desktopCreationCheckIsPending &&
                        'motion-safe:animate-[spin_2s_linear_infinite]'
                    )
                  "
                  :aria-label="t('views.desktops.new-desktop')"
                  class="max-sm:px-[10px]"
                  :disabled="desktopCreationCheckIsPending"
                  @click="goToNewDesktop"
                >
                  <span class="max-sm:hidden">{{ t('views.desktops.new-desktop') }}</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent
                v-if="isSmallScreen"
                :title="t('views.desktops.new-desktop')"
                side="top"
              />
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
      <div v-show="showDesktopFilters" class="flex flex-row w-full gap-4 items-center flex-wrap">
        <div class="flex flex-row gap-2 mr-auto">
          <Toggle v-model="desktopFiltersKindAll" size="desktop" variant="desktops-all">
            <template #default="slotProps">
              {{ t('views.desktops.filters.kind.all') }}
              <BadgeMini
                name="all"
                :value="desktops?.desktops.length || 0"
                :selected="slotProps.pressed"
              />
            </template>
          </Toggle>
          <Toggle
            v-model="desktopFilters.kind.persistent"
            size="desktop"
            variant="desktops-persistent"
          >
            <template #default="slotProps">
              {{
                t(
                  'views.desktops.filters.kind.persistent',
                  desktops?.desktops.filter((d) => d.type === 'persistent' && !d.tag).length || 0
                )
              }}
              <BadgeMini
                name="persistent"
                :value="
                  desktops?.desktops.filter((d) => d.type === 'persistent' && !d.tag).length || 0
                "
                :selected="slotProps.pressed"
              />
            </template>
          </Toggle>
          <Toggle
            v-model="desktopFilters.kind.volatile"
            size="desktop"
            variant="desktops-temporary"
          >
            <template #default="slotProps">
              {{
                t(
                  'views.desktops.filters.kind.nonpersistent',
                  desktops?.desktops.filter((d) => d.type === 'nonpersistent').length || 0
                )
              }}
              <BadgeMini
                name="temporary"
                :value="desktops?.desktops.filter((d) => d.type === 'nonpersistent').length || 0"
                :selected="slotProps.pressed"
              />
            </template>
          </Toggle>
          <Toggle
            v-model="desktopFilters.kind.deployment"
            size="desktop"
            variant="desktops-deployment"
          >
            <template #default="slotProps">
              {{
                t(
                  'views.desktops.filters.kind.deployment',
                  desktops?.desktops.filter((d) => d.tag).length || 0
                )
              }}
              <BadgeMini
                name="deployment"
                :value="desktops?.desktops.filter((d) => d.tag).length || 0"
                :selected="slotProps.pressed"
              />
            </template>
          </Toggle>
        </div>

        <ToggleGroup
          v-model="desktopFilters.status"
          :spacing="1"
          type="single"
          size="default"
          class="bg-base-white border border-1-5 border-gray-warm-300 p-1 rounded-lg"
        >
          <ToggleGroupItem value="all" variant="gray-warm">{{
            t('views.desktops.filters.status.all')
          }}</ToggleGroupItem>
          <ToggleGroupItem value="started" variant="success">{{
            t('views.desktops.filters.status.started')
          }}</ToggleGroupItem>
          <ToggleGroupItem value="stopped" variant="error">{{
            t('views.desktops.filters.status.stopped')
          }}</ToggleGroupItem>
        </ToggleGroup>
      </div>
    </div>

    <div class="flex w-full flex-1 flex-col gap-2">
      <div
        v-if="desktopsIsPending"
        class="grid gap-4 w-full"
        :style="{ gridTemplateColumns: `repeat(auto-fill, minmax(${cardGridMinWidth}px, 1fr))` }"
      >
        <DesktopCardSkeleton variant="started" class="h-[310px]" />
        <DesktopCardSkeleton variant="stopped" class="h-[310px]" />
      </div>

      <p v-else-if="desktopsIsError" class="bg-error-100 text-error-800 p-4 rounded-md">
        <!-- TODO -->
        Error loading desktops: {{ desktopsError?.message }}
      </p>

      <template v-else>
        <EmptyState
          v-show="filteredDesktops.length === 0"
          kind="desktops"
          :variant="isFirstRun ? 'first-run' : 'no-results'"
          :searching="debouncedDesktopSearch.length > 0"
          :active-filters="activeDesktopFilterCount"
          @clear-search="desktopFilters.search = ''"
          @clear-filters="clearDesktopFilters()"
        >
          <template v-if="isFirstRun" #actions>
            <Button
              :icon="desktopCreationCheckIsPending ? 'loading-02' : 'plus'"
              :icon-class="
                cn(desktopCreationCheckIsPending && 'motion-safe:animate-[spin_2s_linear_infinite]')
              "
              :disabled="desktopCreationCheckIsPending"
              size="lg"
              @click="goToNewDesktop"
            >
              {{ t('views.desktops.new-desktop') }}
            </Button>
          </template>
        </EmptyState>

        <DesktopsDataTable
          v-if="viewMode === 'table'"
          v-show="filteredDesktops.length !== 0"
          :desktops="filteredDesktops"
          :prefered-viewers="preferedViewers"
          @desktop-start="(dktp) => desktopStart({ path: { desktop_id: dktp.id } })"
          @desktop-stop="(dktp) => desktopStop({ path: { desktop_id: dktp.id } })"
          @desktop-update-status="
            (dktp) => submitDesktopUpdateStatus({ path: { desktop_id: dktp.id } })
          "
          @desktop-fetch-booking="(dktp) => fetchMaxBookingDate(dktp.id)"
          @open-viewer="
            (data) => fetchAndOpenViewer({ desktopId: data.dktp.id, viewer: data.viewer })
          "
          @show-networks-modal="
            (dktp) => {
              networksModalData = {
                id: dktp.id,
                name: dktp.name,
                ip: dktp.ip,
                status: dktp.status
              }
            }
          "
          @show-info-modal="(dktp) => openDesktopInfoModal(dktp.id)"
          @edit-desktop="(dktp) => goToEditDesktop(dktp.id)"
          @show-delete-modal="
            (dktp) => {
              deleteModalDesktopData = { id: dktp.id, name: dktp.name }
            }
          "
          @show-bastion-modal="
            (dktp) => {
              bastionModalData = { desktopId: dktp.id, desktopName: dktp.name }
            }
          "
          @show-direct-link-modal="(dktp) => showDirectLink(dktp.id)"
          @show-recreate-modal="
            (dktp) => {
              recreateDesktopModalDesktopData = { id: dktp.id, name: dktp.name }
            }
          "
          @create-template="(dktp) => goToNewTemplate(dktp.id)"
          @book-desktop="(dktp) => goToBookingDesktop(dktp.id)"
          @show-storage-modal="(dktp: UserDesktop) => (storageModalDesktop = dktp)"
        />

        <div v-else ref="cardGridRef" class="w-full">
          <!-- Fixed and never re-rendered: the compositor keeps it in place while
               the main thread works, so the fling outruns nothing. Mounted from
               the start, because building it once the fling is on is already
               too late. -->
          <div
            v-show="isFastScrolling && missingCardRows"
            aria-hidden="true"
            class="bg-base-background pointer-events-none fixed bottom-0 z-20 overflow-hidden pt-4"
            :style="{
              top: `${curtainTop}px`,
              left: `${cardGridOffsetLeft}px`,
              width: `${cardGridWidth}px`
            }"
          >
            <div
              class="grid gap-4"
              :style="{ gridTemplateColumns: `repeat(${cardGridColumns}, minmax(0, 1fr))` }"
            >
              <DesktopCardSkeleton
                v-for="n in cardGridColumns * curtainRows"
                :key="n"
                :style="{ height: `${cardGridRowHeight}px` }"
              />
            </div>

            <div class="absolute inset-0 flex items-center justify-center">
              <div
                class="flex flex-col items-center gap-4 rounded-xl bg-base-white/90 px-10 py-8 shadow-lg"
              >
                <Spinner />
                <p class="text-base font-medium text-gray-warm-600">
                  {{ t('views.desktops.loading') }}
                </p>
              </div>
            </div>
          </div>

          <div
            class="relative w-full"
            :style="{ height: `${cardGridVirtualizer.getTotalSize()}px` }"
          >
            <div
              v-for="virtualRow in cardVirtualRows"
              :key="virtualRow.key"
              class="absolute left-0 top-0 grid w-full gap-4"
              :style="{
                gridTemplateColumns: `repeat(${cardGridColumns}, minmax(0, 1fr))`,
                transform: `translateY(${virtualRow.start - cardGridOffsetTop}px)`
              }"
            >
              <DesktopCard
                v-for="dktp in cardGridRows[virtualRow.index]"
                :key="dktp.id"
                :size="cardSize"
                fill
                :desktop="dktp"
                :preferred-viewer="preferedViewers[dktp.id]"
                @desktop-start="desktopStart({ path: { desktop_id: dktp.id } })"
                @desktop-stop="desktopStop({ path: { desktop_id: dktp.id } })"
                @desktop-update-status="
                  submitDesktopUpdateStatus({
                    path: { desktop_id: dktp.id }
                  })
                "
                @desktop-fetch-booking="
                  // handleStartNow(dktp)
                  fetchMaxBookingDate(dktp.id)
                "
                @open-viewer="(viewer) => fetchAndOpenViewer({ desktopId: dktp.id, viewer })"
                @show-networks-modal="
                  networksModalData = {
                    id: dktp.id,
                    name: dktp.name,
                    ip: dktp.ip,
                    status: dktp.status
                  }
                "
                @show-info-modal="openDesktopInfoModal(dktp.id)"
                @edit-desktop="goToEditDesktop(dktp.id)"
                @show-delete-modal="deleteModalDesktopData = { id: dktp.id, name: dktp.name }"
                @show-bastion-modal="
                  bastionModalData = { desktopId: dktp.id, desktopName: dktp.name }
                "
                @show-direct-link-modal="showDirectLink(dktp.id)"
                @show-recreate-modal="
                  recreateDesktopModalDesktopData = { id: dktp.id, name: dktp.name }
                "
                @create-template="goToNewTemplate(dktp.id)"
                @book-desktop="goToBookingDesktop(dktp.id)"
                @show-storage-modal="storageModalDesktop = dktp"
              />
            </div>
          </div>
        </div>
      </template>
    </div>

    <DesktopStorageModal
      :open="storageModalDesktop !== null"
      :desktop="storageModalDesktop ?? undefined"
      @close="storageModalDesktop = null"
    />
  </main>
</template>
