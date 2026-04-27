<script setup lang="ts">
import { computed, readonly, ref, toValue, reactive } from 'vue'

import { useRoute, useRouter, RouterLink } from 'vue-router'
import { useLocalStorage as vueuseLocalStorage, useWindowSize } from '@vueuse/core'
import { useCookies as vueuseCookies } from '@vueuse/integrations/useCookies'
import { useI18n } from 'vue-i18n'
import { useQuery, useQueryClient, useMutation } from '@tanstack/vue-query'
import { useForm } from '@tanstack/vue-form'

import {
  getUserDesktopsApiV4ItemsDesktopsGetQueryKey,
  getUserDesktopsApiV4ItemsDesktopsGetOptions,
  getDesktopViewerApiV4ItemDesktopDesktopIdGetViewerViewerTypeGetOptions,
  getUserConfigApiV4ItemUserGetConfigGetOptions,
  getDesktopNetworksApiV4ItemDesktopDesktopIdGetNetworksGetOptions,
  updateStatusDesktopApiV4ItemDesktopDesktopIdUpdateStatusPutMutation,
  deleteDesktopApiV4ItemDesktopDesktopIdDeleteMutation,
  recreateDesktopApiV4ItemDesktopDesktopIdRecreatePutMutation,
  getRecycleBinDefaultDeleteConfigApiV4ItemRecycleBinGetDefaultDeleteConfigGetOptions,
  getRecycleBinCutoffTimeApiV4ItemRecycleBinGetUserCutoffTimeGetOptions,
  updateDesktopBastionDomainApiV4ItemDesktopDesktopIdUpdateBastionDomainPutMutation,
  updateDesktopBastionAuthorizedKeysApiV4ItemDesktopDesktopIdUpdateBastionAuthorizedKeysPutMutation,
  stopDesktopsApiV4ItemsDesktopsStopPutMutation,
  getMaxBookingDateApiV4ItemBookingMaxBookingDateDesktopIdGetOptions,
  editDesktopApiV4ItemDesktopDesktopIdEditPutMutation,
  createBookingEventApiV4ItemBookingEventPostMutation,
  startDesktopApiV4ItemDesktopDesktopIdStartPutMutation,
  stopDesktopApiV4ItemDesktopDesktopIdStopPutMutation,
  checkQuotaNewDesktopApiV4QuotaDesktopNewGetOptions,
  checkQuotaNewTemplateApiV4QuotaTemplateNewGetOptions,
  checkStoragePoolCreationAvailabilityApiV4StoragePoolsCheckCreateAvailabilityGetOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import {
  startDesktopApiV4ItemDesktopDesktopIdStartPut,
  stopDesktopApiV4ItemDesktopDesktopIdStopPut,
  stopDesktopsApiV4ItemsDesktopsStopPut,
  getDesktopNetworksApiV4ItemDesktopDesktopIdGetNetworksGet,
  getDesktopInfoApiV4ItemDesktopDesktopIdGetDetailsGet,
  deleteDesktopApiV4ItemDesktopDesktopIdDelete,
  getDesktopBastionApiV4ItemDesktopDesktopIdGetBastionGet,
  updateDesktopBastionDomainApiV4ItemDesktopDesktopIdUpdateBastionDomainPut,
  updateDesktopBastionAuthorizedKeysApiV4ItemDesktopDesktopIdUpdateBastionAuthorizedKeysPut,
  getDesktopViewerApiV4ItemDesktopDesktopIdGetViewerViewerTypeGet,
  type GetDesktopViewerApiV4ItemDesktopDesktopIdGetViewerViewerTypeGetData,
  type DesktopBastionResponse,
  type DesktopNetwork,
  type GetDesktopNetworksApiV4ItemDesktopDesktopIdGetNetworksGetData,
  DesktopStatusEnum,
  type UserDesktop,
  getMaxBookingDateApiV4ItemBookingMaxBookingDateDesktopIdGet,
  type ErrorResponse,
  getBookingReservablesAvailableApiV4ItemReservablesGetAvailableGet
} from '@/gen/oas/apiv4/'

import { cn } from '@/lib/utils'
import { QUOTA_STALE_TIME } from '@/lib/constants'
import { sessionTokenName } from '@/lib/auth'
import { withOptimisticItemStatus, withOptimisticItemRemoval } from '@/lib/optimistic'

import desktopsEmptyImg from '@/assets/img/desktops-empty.svg'

import { SinglePageLayout } from '@/layouts/single-page'

import {
  DomainInfoModal,
  DirectViewerModal,
  DesktopBastionInfoModal,
  DesktopNetworksModal
} from '@/components/desktops'
import ChangeImageModal from '@/components/domain/ChangeImageModal.vue'
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
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
  FieldError
} from '@/components/ui/field'
import { Icon, CopyIcon } from '@/components/icon'
import { InputField } from '@/components/input-field'
import { Label } from '@/components/ui/label'
import { AlertModal, Modal, QuotaExceededModal } from '@/components/modal'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
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
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Toggle } from '@/components/ui/toggle'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ViewerSelect } from '@/components/viewer-select'

const { t, d } = useI18n()
const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

const cookies = vueuseCookies(['viewerToken', 'browser_viewer', sessionTokenName])
const localStorage = vueuseLocalStorage('viewers', '')

const {
  isPending: desktopsIsPending,
  isError: desktopsIsError,
  error: desktopsError,
  data: desktops
} = useQuery(getUserDesktopsApiV4ItemsDesktopsGetOptions())

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
} = useQuery(getUserConfigApiV4ItemUserGetConfigGetOptions())

const {
  isPending: recycleBinDefaultDeleteIsPending,
  isError: recycleBinDefaultDeleteIsError,
  error: recycleBinDefaultDeleteError,
  data: recycleBinDefaultDelete
} = useQuery(getRecycleBinDefaultDeleteConfigApiV4ItemRecycleBinGetDefaultDeleteConfigGetOptions())

const {
  isPending: recycleBinCutoffTimeIsPending,
  isError: recycleBinCutoffTimeIsError,
  error: recycleBinCutoffTimeError,
  data: recycleBinCutoffTime
} = useQuery(getRecycleBinCutoffTimeApiV4ItemRecycleBinGetUserCutoffTimeGetOptions())

const quotaExceededModalData = ref<{
  title: string
  description: string
  cancelLabel: string
} | null>(null)

const desktopsKey = getUserDesktopsApiV4ItemsDesktopsGetQueryKey()

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
    baseMutation: startDesktopApiV4ItemDesktopDesktopIdStartPutMutation(),
    onError: (error) => {
      const err = error as ErrorResponse
      if (err.description_code === 'desktop_start_user_quota_exceeded') {
        quotaExceededModalData.value = {
          title: t('components.desktops.start-quota-exceeded-modal.title'),
          description: t('components.desktops.start-quota-exceeded-modal.description'),
          cancelLabel: t('components.desktops.start-quota-exceeded-modal.cancel')
        }
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
    baseMutation: stopDesktopApiV4ItemDesktopDesktopIdStopPutMutation()
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
    baseMutation: updateStatusDesktopApiV4ItemDesktopDesktopIdUpdateStatusPutMutation()
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
  ...stopDesktopsApiV4ItemsDesktopsStopPutMutation(),
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
  mutationFn: async (desktopId: string) => {
    const { data } = await getDesktopInfoApiV4ItemDesktopDesktopIdGetDetailsGet({
      path: {
        desktop_id: desktopId
      },
      throwOnError: true
    })
    return data
  }
})

const openDesktopInfoModal = async (desktopId: string) => {
  fetchDesktopDetails(desktopId)
  showDesktopInfoModal.value = true
}

// --------------------------------------------------

const deleteModalDesktopData = ref<{
  id: string
  name: string
} | null>(null)
const deleteModalRecicleBinChecked = ref(recycleBinDefaultDelete.value)

const {
  mutate: deleteDesktop,
  mutateAsync: deleteDesktopAsync,
  isPending: deleteDesktopIsPending,
  isError: deleteDesktopIsError,
  error: deleteDesktopError
} = useMutation(
  withOptimisticItemRemoval<{ path: { desktop_id: string } }, UserDesktop, 'desktops'>({
    queryClient,
    queryKey: desktopsKey,
    listKey: 'desktops',
    extractItemId: (vars) => vars.path.desktop_id,
    baseMutation: deleteDesktopApiV4ItemDesktopDesktopIdDeleteMutation(),
    onSuccess: () => {
      closeDeleteModal()
    }
  })
)

const closeDeleteModal = () => {
  deleteModalRecicleBinChecked.value = recycleBinDefaultDelete.value
  deleteModalDesktopData.value = null
}

// --------------------------------------------------

const recreateDesktopModalDesktopData = ref<{
  id: string
  name: string
} | null>(null)

const {
  mutate: recreateDesktop,
  mutateAsync: recreateDesktopAsync,
  isPending: recreateDesktopIsPending,
  isError: recreateDesktopIsError,
  error: recreateDesktopError
} = useMutation({
  ...recreateDesktopApiV4ItemDesktopDesktopIdRecreatePutMutation(),
  onSuccess: () => {
    closeRecreateDesktopModal()
  }
})

const closeRecreateDesktopModal = () => {
  recreateDesktopModalDesktopData.value = null
}

// --------------------------------------------------

interface BastionModalData {
  desktopId: string
  desktopName: string
}
const bastionModalData = ref<BastionModalData | null>(null)

// --------------------------------------------------

const preferedViewers = computed(() => {
  // TODO: move this to the card component
  if (localStorage.value) {
    return JSON.parse(localStorage.value)
  }
  return {}
})

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

// In-flight de-dup: a SPICE viewer download triggers `virt-viewer` to open
// a new SPICE session, and SPICE servers don't multiplex by default — a
// second viewer kicks the first. Coalesce overlapping clicks for the same
// (desktop, viewer_type) so a double-click produces one .vv, not two.
const viewerFetchInflight = new Map<string, Promise<void>>()

const fetchAndOpenViewer = (
  desktopId: string,
  viewer: GetDesktopViewerApiV4ItemDesktopDesktopIdGetViewerViewerTypeGetData['path']['viewer_type']
): Promise<void> => {
  // TODO: use a mutation
  const key = `${desktopId}:${viewer}`
  const existing = viewerFetchInflight.get(key)
  if (existing) return existing

  const run = async () => {
    const { error, data } = await getDesktopViewerApiV4ItemDesktopDesktopIdGetViewerViewerTypeGet({
      path: {
        desktop_id: desktopId,
        viewer_type: viewer
      }
    })

    if (error) {
      console.error('Error fetching desktop info:', error)
      return
    }

    // store prefered viewer in localStorage
    const updatedPreferedViewers = {
      ...preferedViewers.value,
      [desktopId]: viewer
    }
    localStorage.value = JSON.stringify(updatedPreferedViewers)

    if (data.kind === 'browser') {
      const cookieOpts: CookieSetOptions = {
        path: '/',
        sameSite: 'strict'
      }

      if (data.protocol === 'rdp') {
        cookies.set('viewerToken', cookies.get(sessionTokenName), cookieOpts)
      }
      cookies.set('browser_viewer', data.cookie, cookieOpts)

      window.open(data.viewer || undefined, '_blank')
    } else if (data.kind === 'file') {
      // TODO: check if this can be done without creating an element
      const el = document.createElement('a')
      el.setAttribute(
        'href',
        `data:${data.mime};charset=utf-8,${encodeURIComponent(data.content || '')}`
      )
      el.setAttribute('download', `${data.name}.${data.ext}`)
      el.style.display = 'none'
      document.body.appendChild(el)
      el.click()
      document.body.removeChild(el)
    }
  }

  const promise = run().finally(() => {
    viewerFetchInflight.delete(key)
  })
  viewerFetchInflight.set(key, promise)
  return promise
}

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

const clearDesktopFilters = () => {
  desktopFilters.value = JSON.parse(JSON.stringify(defaultDesktopFilters))
}

const filteredDesktops = computed(() => {
  return (
    desktops.value?.desktops.filter((desktop) => {
      return isDesktopVisible(desktop)
    }) || []
  )
})

const isDesktopVisible = (desktop: UserDesktop) => {
  // Search filter
  const matchesSearch =
    desktopFilters.value.search.toLowerCase() === '' ||
    desktop.name.toLowerCase().includes(desktopFilters.value.search.toLowerCase()) ||
    desktop.description?.toLowerCase().includes(desktopFilters.value.search.toLowerCase())

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
      (
        [
          DesktopStatusEnum.STARTING,
          DesktopStatusEnum.STARTED,
          DesktopStatusEnum.SHUTTING_DOWN,
          DesktopStatusEnum.WAITING_IP
        ] as DesktopStatusEnum[]
      ).includes(desktop.status)) ||
    (desktopFilters.value.status === 'stopped' &&
      !(
        [
          DesktopStatusEnum.STARTING,
          DesktopStatusEnum.STARTED,
          DesktopStatusEnum.SHUTTING_DOWN,
          DesktopStatusEnum.WAITING_IP
        ] as DesktopStatusEnum[]
      ).includes(desktop.status))

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
    const { data } = await getMaxBookingDateApiV4ItemBookingMaxBookingDateDesktopIdGet({
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
          currentGpu: desktop.reservables?.vgpus?.[0] || 'N/A'
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
    const { data } = await getBookingReservablesAvailableApiV4ItemReservablesGetAvailableGet({
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
} | null>(null)

const changeAndStartModalData = ref<{
  id: string
  name: string
  currentGpu: string
} | null>(null)

const {
  mutate: editDesktop,
  mutateAsync: editDesktopAsync,
  isPending: editDesktopIsPending,
  isError: editDesktopIsError,
  error: editDesktopError
} = useMutation(editDesktopApiV4ItemDesktopDesktopIdEditPutMutation())

const {
  mutate: createBookingEvent,
  mutateAsync: createBookingEventAsync,
  isPending: createBookingEventIsPending,
  isError: createBookingEventIsError,
  error: createBookingEventError
} = useMutation(createBookingEventApiV4ItemBookingEventPostMutation())

const changeAndStartForm = useForm({
  defaultValues: {
    profile: '',
    end_time: ''
  },
  onSubmit: async ({ value }) => {
    try {
      await editDesktopAsync({
        path: { desktop_id: changeAndStartModalData.value!.id },
        body: {
          reservables: {
            vgpus: [value.profile]
          }
        }
      })

      try {
        await createBookingEventAsync({
          body: {
            end: new Date(value.end_time).toISOString(),
            item_id: changeAndStartModalData.value!.id,
            start: new Date().toISOString(),
            now: true,
            item_type: 'desktop'
          }
        })

        desktopStart({ path: { desktop_id: changeAndStartModalData.value!.id } })
        closeChangeAndStartModal()
      } catch (bookingError) {
        console.error('Error creating booking event:', bookingError)
      }
    } catch (error) {
      console.error('Error editing desktop:', error)
      return
    }
  }
})
const changeAndStartModalSelectedProfile = changeAndStartForm.useStore(
  (state) => state.values.profile
)
const changeAndStartModalSelectedProfile2 = ref<string>('')

const closeChangeAndStartModal = () => {
  changeAndStartModalData.value = null
  changeAndStartForm.reset()
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

const getEndTimeIntervals = (endTime: Date): Date[] => {
  const currentTime = new Date()
  if (endTime <= currentTime) {
    return []
  }

  currentTime.setMinutes(currentTime.getMinutes() + 30)
  if (endTime <= currentTime) {
    return [endTime]
  }

  const intervals: Date[] = []
  while (currentTime < endTime) {
    intervals.push(new Date(currentTime))
    currentTime.setMinutes(currentTime.getMinutes() + 30)
  }

  return intervals
}

const maxBookingDateEndTimeIntervals = computed<Date[]>(() => {
  if (!maxBookingDate.value) {
    return []
  }

  const maxDate = new Date(maxBookingDate.value.max_booking_date)
  return getEndTimeIntervals(maxDate)
})

const changeAndStartModalSelectedProfileEndTimeIntervals = computed<Date[]>(() => {
  if (!changeAndStartModalSelectedProfile2.value) {
    return []
  }

  const maxDate = new Date(
    availableReservables.value?.reservables_available?.find(
      (r) => r.id === changeAndStartModalSelectedProfile2.value
    )?.max_booking_date || ''
  )
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
      ...checkQuotaNewDesktopApiV4QuotaDesktopNewGetOptions(),
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
      ...checkStoragePoolCreationAvailabilityApiV4StoragePoolsCheckCreateAvailabilityGetOptions(),
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
  router.push({ name: 'booking', params: { type: 'desktop', id: desktopId } })
}

const changeImageModalData = ref<{
  desktopId: string
  currentImage?: { id: string; type: string; url?: string }
} | null>(null)

const openChangeImageModal = (desktop: {
  id: string
  image?: { id: string; type: string; url?: string }
}) => {
  changeImageModalData.value = {
    desktopId: desktop.id,
    currentImage: desktop.image
  }
}

const templateCreationCheckIsPending = ref(false)

const goToNewTemplate = async (desktopId: string) => {
  templateCreationCheckIsPending.value = true
  try {
    await queryClient.fetchQuery({
      ...checkQuotaNewTemplateApiV4QuotaTemplateNewGetOptions(),
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

const { width: windowWidth } = useWindowSize()

const cardSize = computed<CardSize>(() => {
  if (windowWidth.value < 1280) return 'md'
  return 'lg'
})

const cardGridMinWidth = computed(() => (cardSize.value === 'md' ? '250px' : '412px'))
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
          deleteDesktop({
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

  <ChangeImageModal
    v-if="changeImageModalData !== null"
    :open="changeImageModalData !== null"
    :desktop-id="changeImageModalData.desktopId"
    :current-image="changeImageModalData.currentImage"
    @close="changeImageModalData = null"
    @saved="changeImageModalData = null"
  />

  <DomainInfoModal
    :open="showDesktopInfoModal"
    :domain-id="desktopDetailsDesktopId"
    :name="desktopDetails?.name || ''"
    :description="desktopDetails?.description"
    :status="desktopDetails?.status"
    :ip="desktopDetails?.ip"
    :vcpu="desktopDetails?.vcpu"
    :ram="desktopDetails?.memory"
    :boot-order="desktopDetails?.boot_order.map((bo) => bo.name)"
    :disk-bus="desktopDetails?.disk_bus"
    :vga="desktopDetails?.videos.map((vga) => vga.name)"
    :viewers="desktopDetails?.viewers"
    :isos="desktopDetails?.isos?.map((iso) => iso.name)"
    :floppies="desktopDetails?.floppies?.map((floppy) => floppy.name)"
    :reservables="desktopDetails?.reservables?.vgpus"
    :kind="'desktop'"
    :template="desktopDetails?.template"
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
  <AlertModal
    :open="recreateDesktopModalDesktopData !== null"
    level="warning"
    size="lg"
    :title="
      t('components.recreate-desktop-confirmation-modal.title', {
        name: recreateDesktopModalDesktopData?.name
      })
    "
    :description="t('components.recreate-desktop-confirmation-modal.description')"
    @close="closeRecreateDesktopModal()"
  >
    <!-- TODO: Recreate modal component -->
    <template #footer>
      <Button hierarchy="link-gray" @click="closeRecreateDesktopModal()">{{
        t('components.recreate-desktop-confirmation-modal.cancel')
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
        {{ t('components.recreate-desktop-confirmation-modal.confirm') }}
      </Button>
    </template>
  </AlertModal>

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

  <!-- TODO: custom modal component instead of AlertModal -->
  <!-- Change and Start modal -->
  <Modal
    v-if="changeAndStartModalData !== null"
    :open="changeAndStartModalData !== null"
    class="pt-4 min-w-120"
    :title="t('components.desktop-gpu-change-and-start-modal.title')"
    @close="closeChangeAndStartModal()"
  >
    <div v-if="true" class="mt-4 flex flex-col gap-4">
      {{ t('components.desktop-gpu-change-and-start-modal.description') }}

      <!-- TODO: If availableReservables <= 5, show buttons for each gpu, else show a dropdown. -->
      <!-- TODO: use tanstack form -->

      {{ changeAndStartModalSelectedProfile }}

      <!-- <Button @click="changeAndStartForm.reset()">Reset form</Button> -->

      <div
        v-if="getAvailableReservablesIsPending"
        class="w-full flex flex-col items-start justify-start gap-2"
      >
        <Skeleton class="h-4 w-1/4" />
        <Skeleton class="h-8 w-full" />
      </div>

      <Empty v-else-if="!availableReservables" class="gap-2">
        <EmptyHeader>
          <EmptyMedia variant="default" class="select-none pointer-events-none">
            <Icon name="alert-triangle" class="size-12" stroke-color="warning-600" />
          </EmptyMedia>
        </EmptyHeader>
        <EmptyTitle class="font-semibold">{{
          t('components.desktop-gpu-change-and-start-modal.empty.title')
        }}</EmptyTitle>
        <EmptyDescription class="">{{
          t('components.desktop-gpu-change-and-start-modal.empty.description', {
            kind: t('domains.desktops', 0)
          })
        }}</EmptyDescription>
      </Empty>

      <form
        v-else
        id="change-and-start-form"
        class="flex flex-row items-center gap-2 w-full"
        @submit.prevent.stop="changeAndStartForm.handleSubmit"
      >
        <FieldGroup class="gap-4">
          <changeAndStartForm.Field
            name="profile"
            :listeners="{
              onChange: ({ value }) => {
                if (value !== changeAndStartModalSelectedProfile2) {
                  changeAndStartModalSelectedProfile2 = value
                }
              }
            }"
          >
            <template #default="{ field }">
              <Field :data-invalid="isInvalid(field)">
                <FieldLabel :for="field.name">{{
                  t('components.desktop-gpu-change-and-start-modal.gpu-select.label')
                }}</FieldLabel>
                <!--  -->
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
                      :placeholder="
                        t('components.desktop-gpu-change-and-start-modal.gpu-select.placeholder')
                      "
                    />
                  </SelectTrigger>
                  <SelectContent class="left-0 right-0">
                    <SelectGroup>
                      <SelectItem
                        v-for="profile in availableReservables?.reservables_available"
                        :key="profile.id"
                        :value="profile.id"
                      >
                        {{
                          t('components.desktop-gpu-change-and-start-modal.gpu-select.value', {
                            profile: profile.name
                          })
                        }}
                      </SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>

                <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
              </Field>
            </template>
          </changeAndStartForm.Field>

          <template v-if="changeAndStartModalSelectedProfile">
            <changeAndStartForm.Field name="end_time">
              <template #default="{ field }">
                <Field :data-invalid="isInvalid(field)">
                  <!-- TODO: maybe centralise this select -->
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
                          v-for="endTime in changeAndStartModalSelectedProfileEndTimeIntervals"
                          :key="endTime.toISOString()"
                          _v-for="endTime in getEndTimeIntervals(
                            new Date(
                              // changeAndStartModalSelectedProfile.max_booking_date
                              availableReservables?.reservables_available?.find(
                                (r) => r.id === changeAndStartModalSelectedProfile2
                              )?.max_booking_date || new Date().toISOString()
                            )
                          )"
                          :value="endTime.toISOString()"
                        >
                          {{ d(endTime, { timeStyle: 'short' }) }}
                        </SelectItem>
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </Field>
              </template>
            </changeAndStartForm.Field>
          </template>
        </FieldGroup>
      </form>
    </div>
    <template #footer>
      <Button hierarchy="link-gray" @click="closeChangeAndStartModal()">{{
        t('components.desktop-gpu-change-and-start-modal.cancel')
      }}</Button>

      <Button
        v-if="true"
        hierarchy="primary"
        :disabled="editDesktopIsPending || createBookingEventIsPending"
        type="submit"
        form="change-and-start-form"
      >
        <Icon
          v-if="editDesktopIsPending || createBookingEventIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        <Icon v-else name="play" stroke-color="currentColor" />
        {{ t('components.desktop-gpu-change-and-start-modal.confirm') }}
      </Button>
      <Button
        v-else
        hierarchy="primary"
        :disabled="recreateDesktopIsPending"
        @click="recreateDesktop({ path: { desktop_id: recreateDesktopModalDesktopData!.id } })"
      >
        <!-- TODO: book button if no available profiles: get-available 428 no_available_profile -->
        <Icon
          v-if="recreateDesktopIsPending"
          class="motion-safe:animate-[spin_2s_linear_infinite]"
          name="loading-02"
          stroke-color="currentColor"
        />
        <Icon v-else name="calendar-plus-02" stroke-color="currentColor" />
        {{ t('components.desktop-gpu-change-and-start-modal.book') }}
      </Button>
    </template>
  </Modal>

  <main v-if="route.params.desktopId" class="w-full h-full flex justify-center items-center">
    <Empty>
      <EmptyTitle class="text-display-md! font-bold text-gray-warm-800">{{
        t(`views.desktops.${route.params.action}.title`, { kind: t('domains.desktops', 0) })
      }}</EmptyTitle>
      <EmptyDescription class="-mt-3 text-md text-gray-warm-600">{{
        t(`views.desktops.${route.params.action}.description`, { kind: t('domains.desktops', 0) })
      }}</EmptyDescription>

      <DesktopCard
        v-if="routeDesktop"
        class="mt-6 text-start"
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
        @open-viewer="fetchAndOpenViewer(routeDesktop.id, $event)"
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
        @change-image="openChangeImageModal(routeDesktop)"
        @show-storage-modal="storageModalDesktop = routeDesktop"
      />

      <EmptyContent class="flex-row">
        <Button hierarchy="link-color" :as="RouterLink" :to="{ name: 'desktops' }">{{
          t('views.desktops.go-to-desktops')
        }}</Button>
        <Button
          :icon="desktopCreationCheckIsPending ? 'loading-02' : 'plus'"
          :icon-class="
            cn(desktopCreationCheckIsPending && 'motion-safe:animate-[spin_2s_linear_infinite]')
          "
          :disabled="desktopCreationCheckIsPending"
          @click="goToNewDesktop"
        >
          {{ t('views.desktops.new-desktop') }}
        </Button>
      </EmptyContent>
    </Empty>
  </main>

  <main v-else class="flex flex-col gap-3 p-3 w-full">
    <div class="flex flex-row w-full gap-4 items-center flex-wrap">
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
        <Toggle v-model="desktopFilters.kind.volatile" size="desktop" variant="desktops-temporary">
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

      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              hierarchy="destructive"
              icon="stop"
              :disabled="!anyDesktopStarted"
              @click="showStopAllDesktopsModal = true"
              >{{ t('views.desktops.stop-all') }}</Button
            >
          </TooltipTrigger>
          <TooltipContent
            v-if="!anyDesktopStarted"
            :title="t('views.desktops.stop-all-tooltip.title')"
            side="top"
          />
        </Tooltip>
      </TooltipProvider>
      <Button
        :icon="desktopCreationCheckIsPending ? 'loading-02' : 'plus'"
        :icon-class="
          cn(desktopCreationCheckIsPending && 'motion-safe:animate-[spin_2s_linear_infinite]')
        "
        :disabled="desktopCreationCheckIsPending"
        @click="goToNewDesktop"
      >
        {{ t('views.desktops.new-desktop') }}
      </Button>
    </div>
    <div class="flex flex-row w-full gap-4 items-start flex-wrap">
      <InputField
        v-model="desktopFilters.search"
        :placeholder="t('views.desktops.filters.search.placeholder')"
        icon="search-lg"
        class="h-full w-full max-w-120 mr-auto"
      />
      <!-- <Input class="max-w-120 mr-auto" placeholder="Search Desktop" /> -->

      <Button
        hierarchy="secondary-gray"
        :icon="viewMode === 'cards' ? 'rows-01' : 'grid-01'"
        class="p-[10px]"
        @click="viewMode = viewMode === 'cards' ? 'table' : 'cards'"
      />

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

    <div class="flex flex-col gap-2 flex-wrap w-full">
      <div
        v-if="desktopsIsPending"
        class="grid gap-4 w-full"
        :style="{ gridTemplateColumns: `repeat(auto-fill, minmax(${cardGridMinWidth}, 1fr))` }"
      >
        <DesktopCardSkeleton variant="started" class="h-[310px]" />
        <DesktopCardSkeleton variant="stopped" class="h-[310px]" />
      </div>

      <p v-else-if="desktopsIsError" class="bg-error-100 text-error-800 p-4 rounded-md">
        <!-- TODO -->
        Error loading desktops: {{ desktopsError?.message }}
      </p>

      <template v-else>
        <Empty v-show="filteredDesktops.length === 0">
          <EmptyHeader>
            <EmptyMedia variant="default" class="select-none pointer-events-none">
              <img :src="desktopsEmptyImg" />
            </EmptyMedia>
          </EmptyHeader>
          <EmptyTitle class="text-[30px] font-bold">{{
            t('components.empty.title', { kind: t('domains.desktops', 0) })
          }}</EmptyTitle>
          <EmptyDescription class="text-[18px]!">{{
            t('components.empty.description', { kind: t('domains.desktops', 0) })
          }}</EmptyDescription>
          <EmptyContent class="flex-row">
            <Button
              v-show="areDesktopFiltersActive && desktops?.desktops.length"
              hierarchy="secondary-color"
              icon="filter-funnel-02"
              @click="clearDesktopFilters()"
              >{{ t('components.empty.clear-filters') }}</Button
            >
            <Button
              :icon="desktopCreationCheckIsPending ? 'loading-02' : 'plus'"
              :icon-class="
                cn(desktopCreationCheckIsPending && 'motion-safe:animate-[spin_2s_linear_infinite]')
              "
              :disabled="desktopCreationCheckIsPending"
              @click="goToNewDesktop"
            >
              {{ t('views.desktops.new-desktop') }}
            </Button>
          </EmptyContent>
        </Empty>

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
          @open-viewer="(data) => fetchAndOpenViewer(data.dktp.id, data.viewer)"
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
          @change-image="(dktp) => openChangeImageModal(dktp)"
          @show-storage-modal="(dktp: UserDesktop) => (storageModalDesktop = dktp)"
        />

        <div
          v-else
          class="grid gap-4 w-full"
          :style="{ gridTemplateColumns: `repeat(auto-fill, minmax(${cardGridMinWidth}, 1fr))` }"
        >
          <template v-for="dktp in desktops?.desktops" :key="dktp.id">
            <DesktopCard
              v-show="isDesktopVisible(dktp)"
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
              @open-viewer="fetchAndOpenViewer(dktp.id, $event)"
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
              @change-image="openChangeImageModal(dktp)"
              @show-storage-modal="storageModalDesktop = dktp"
            />
          </template>
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
