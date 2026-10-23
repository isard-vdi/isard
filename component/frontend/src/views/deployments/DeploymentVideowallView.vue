<script setup lang="ts">
import { computed, provide, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import {
  useElementSize,
  useElementVisibility,
  useLocalStorage,
  useWindowScroll,
  useWindowSize
} from '@vueuse/core'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import {
  getDesktopDetailsOptions,
  getDeploymentVideowallOptions,
  getDeploymentVideowallQueryKey,
  startDesktopMutation,
  stopDesktopMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { AvatarLabel } from '@/components/avatar-label'
import { Icon } from '@/components/icon'
import {
  FilterTags,
  countFilterTags,
  emptyFilterTags,
  type FilterCategory
} from '@/components/filter-tags'
import {
  DesktopCard,
  DesktopCardSkeleton,
  PREVIEWS_PAUSED_INJECTION_KEY,
  overlayIconButtonClass,
  type CardSize,
  type OverlayKind
} from '@/components/desktop-card'
import { DesktopsDataTable } from '@/components/desktops-data-table'
import {
  DesktopBastionInfoModal,
  DesktopNetworksModal,
  DomainInfoModal
} from '@/components/desktops'
import { VideowallViewerModal, type ViewerLayout } from '@/components/deployments/videowall-viewer'
import { EmptyState, PageContainer, PageToolbar, SearchInput } from '@/components/page'
import { TruncatedText } from '@/components/truncated-text'
import { useFetchAndOpenViewer } from '@/composables/useFetchAndOpenViewer'
import { useStopAllDesktops } from '@/composables/useStopAllDesktops'
import { StopAllDesktopsModal } from '@/components/modal'
import { DesktopStatusEnum, type UserDeploymentDesktop } from '@/gen/oas/apiv4'
import { withOptimisticItemStatus } from '@/lib/optimistic'
import {
  canViewInBrowser,
  countVideowallStatuses,
  groupVideowallDesktops,
  isRunning,
  toVideowallDesktop,
  videowallDesktopKey,
  type VideowallDesktop,
  type VideowallGroupBy
} from '@/lib/videowall'
import { cn } from '@/lib/utils'
import { describeApiError } from '@/lib/api-errors'
import { toast } from '@/components/ui/toast'

const route = useRoute()
const { t, te } = useI18n()
const queryClient = useQueryClient()

const deploymentId = computed(() => route.params.deploymentId as string)

const { data: deployment, isPending } = useQuery(
  getDeploymentVideowallOptions({
    path: { deployment_id: deploymentId.value }
  })
)

const viewMode = useLocalStorage<'cards' | 'table'>('videowall-view-mode', 'cards')
const groupBy = useLocalStorage<VideowallGroupBy>('videowall-group-by', 'user')
const groupByOptions = computed<{ value: VideowallGroupBy; label: string; icon: string }[]>(() => [
  { value: 'user', label: t('views.deployment-videowall.group-by.user'), icon: 'user-01' },
  {
    value: 'desktop',
    label: t('views.deployment-videowall.group-by.desktop'),
    icon: 'monitor-02'
  }
])
const selectedGroupByOption = computed(() =>
  groupByOptions.value.find((option) => option.value === groupBy.value)
)
const VIDEOWALL_SEARCH_INPUT_ID = 'deployment-videowall-search'
const filterText = ref('')

const FILTER_CATEGORIES = ['status', 'desktop']
const filterTags = ref(emptyFilterTags(FILTER_CATEGORIES))

const allDesktops = computed(() => (deployment.value?.desktops ?? []).map(toVideowallDesktop))

// The whole deployment, filters aside: "stop all" acts on every desktop.
const stopCounts = computed(() => {
  const count = (...statuses: string[]) =>
    allDesktops.value.filter((d) => statuses.includes(d.status)).length
  return {
    started: count(
      DesktopStatusEnum.STARTING,
      DesktopStatusEnum.STARTED,
      DesktopStatusEnum.WAITING_IP
    ),
    shuttingDown: count(DesktopStatusEnum.SHUTTING_DOWN),
    stopping: count(DesktopStatusEnum.STOPPING)
  }
})
const {
  showStopAllModal,
  stopAllError,
  stopAllIsPending,
  anyDesktopStoppable,
  isStoppingAll,
  openStopAllModal,
  closeStopAllModal,
  confirmStopAll
} = useStopAllDesktops(deploymentId, stopCounts)

const filterCategories = computed<FilterCategory[]>(() => {
  const started = allDesktops.value.filter(isRunning).length
  // The same entries, order and labels as grouping by desktop.
  const deploymentDesktops = groupVideowallDesktops(
    allDesktops.value,
    'desktop',
    deployment.value?.deployment_desktops ?? []
  )
  return [
    {
      key: 'status',
      label: t('views.deployment-videowall.filters.status.label'),
      options: [
        {
          value: 'started',
          label: t('views.deployment-videowall.filters.status.started'),
          count: started,
          icon: 'play'
        },
        {
          value: 'stopped',
          label: t('views.deployment-videowall.filters.status.stopped'),
          count: allDesktops.value.length - started,
          icon: 'stop'
        }
      ]
    },
    {
      key: 'desktop',
      label: t('views.deployment-videowall.filters.desktop.label'),
      options: deploymentDesktops.map((group) => ({
        value: group.key,
        label: group.label,
        count: group.desktops.length,
        icon: 'monitor-02'
      }))
    }
  ]
})

const desktops = computed<VideowallDesktop[]>(() => {
  const statuses = filterTags.value.status ?? []
  const deploymentDesktops = filterTags.value.desktop ?? []
  const needle = filterText.value.trim().toLowerCase()
  return allDesktops.value.filter(
    (d) =>
      (statuses.length === 0 || statuses.includes(isRunning(d) ? 'started' : 'stopped')) &&
      (deploymentDesktops.length === 0 || deploymentDesktops.includes(videowallDesktopKey(d))) &&
      (!needle ||
        d.user_name.toLowerCase().includes(needle) ||
        d.name.toLowerCase().includes(needle))
  )
})

const activeFilterCount = computed(() => countFilterTags(filterTags.value))
// The search and tags in words, or null when unfiltered.
const filterSummary = computed(() => {
  const needle = filterText.value.trim()
  const parts = needle ? [`"${needle}"`] : []
  for (const category of filterCategories.value) {
    const selected = filterTags.value[category.key] ?? []
    parts.push(...category.options.filter((o) => selected.includes(o.value)).map((o) => o.label))
  }
  return parts.length > 0 ? parts.join(' · ') : null
})
const clearFilters = () => {
  filterText.value = ''
  filterTags.value = emptyFilterTags(FILTER_CATEGORIES)
}

const groups = computed(() =>
  groupVideowallDesktops(desktops.value, groupBy.value, deployment.value?.deployment_desktops ?? [])
)
const groupStatuses = computed(
  () => new Map(groups.value.map((g) => [g.key, countVideowallStatuses(g.desktops)]))
)
// Only what needs an eye: stopped is whatever is neither.
const GROUP_STATUSES = [
  { key: 'started', dot: 'bg-success-500' },
  { key: 'failed', dot: 'bg-error-500' }
] as const
// Same fallback as AvatarLabel.
const initials = (name: string) =>
  name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()

// Same card sizes as the desktops view.
const { width: windowWidth } = useWindowSize()
const cardSize = computed<CardSize>(() => (windowWidth.value < 1280 ? 'md' : 'lg'))
const cardMinWidth = computed(() => (cardSize.value === 'md' ? 250 : 412))
// Tailwind `gap-4`.
const CARD_GAP = 16
const cardOverlays = ref<Record<string, OverlayKind | null>>({})

const cardGridRef = ref<HTMLElement | null>(null)
const { width: cardGridWidth } = useElementSize(cardGridRef)
// As many columns as fit, like the desktops view: wide windows add cards, not width.
const cardColumns = computed(() =>
  Math.max(1, Math.floor((cardGridWidth.value + CARD_GAP) / (cardMinWidth.value + CARD_GAP)))
)

// The toolbar sticks under the page header (h-16), as in the desktops view.
const PAGE_HEADER_HEIGHT = 64
const toolbarRef = ref<HTMLElement | null>(null)
const { height: toolbarHeight } = useElementSize(toolbarRef, undefined, { box: 'border-box' })
const { y: windowScrollY } = useWindowScroll()
// A desktop group's heading sticks under the toolbar, which may wrap.
const groupHeaderTop = computed(() => `${PAGE_HEADER_HEIGHT + toolbarHeight.value}px`)
// Once the heading is gone under the page header, the toolbar carries a compact copy.
const headingRef = ref<HTMLElement | null>(null)
const headingVisible = useElementVisibility(headingRef, {
  initialValue: true,
  rootMargin: `-${PAGE_HEADER_HEIGHT}px 0px 0px 0px`
})

// A table per user would hold one or two rows each: one table, ordered by user.
const tableGroups = computed(() =>
  groupBy.value === 'user'
    ? [{ key: 'all', label: '', desktops: groups.value.flatMap((g) => g.desktops) }]
    : groups.value
)

const videowallKey = getDeploymentVideowallQueryKey({
  path: { deployment_id: deploymentId.value }
})

const { mutate: startDesktop } = useMutation(
  withOptimisticItemStatus<{ path: { desktop_id: string } }, UserDeploymentDesktop, 'desktops'>({
    queryClient,
    queryKey: videowallKey,
    listKey: 'desktops',
    extractItemId: (vars) => vars.path.desktop_id,
    nextStatus: DesktopStatusEnum.STARTING,
    // Only Stopped/Failed accept a start, as in DesktopEvents.desktop_start.
    nextStatusGuard: (current) =>
      current === DesktopStatusEnum.STOPPED || current === DesktopStatusEnum.FAILED,
    baseMutation: startDesktopMutation(),
    // A wall starts many desktops in a row: a toast, not a modal per failure.
    onError: (error) => toast.error(describeApiError(error, { t, te }, 'start-desktop'))
  })
)
const { mutate: stopDesktop } = useMutation(
  withOptimisticItemStatus<{ path: { desktop_id: string } }, UserDeploymentDesktop, 'desktops'>({
    queryClient,
    queryKey: videowallKey,
    listKey: 'desktops',
    extractItemId: (vars) => vars.path.desktop_id,
    nextStatus: DesktopStatusEnum.STOPPING,
    nextStatusGuard: (current) =>
      current === DesktopStatusEnum.STARTED ||
      current === DesktopStatusEnum.WAITING_IP ||
      current === DesktopStatusEnum.SHUTTING_DOWN ||
      current === DesktopStatusEnum.PAUSED ||
      current === DesktopStatusEnum.SUSPENDED,
    baseMutation: stopDesktopMutation(),
    onError: (error) => toast.error(describeApiError(error, { t, te }, 'stop-desktop'))
  })
)
const { mutate: fetchAndOpenViewer, preferedViewers } = useFetchAndOpenViewer()

const showDesktopInfoModal = ref(false)
const {
  mutate: fetchDesktopDetails,
  isPending: fetchDesktopDetailsIsPending,
  data: desktopDetails,
  variables: desktopDetailsDesktopId,
  reset: resetDesktopDetails
} = useMutation({
  mutationFn: (desktopId: string) =>
    queryClient.fetchQuery(
      getDesktopDetailsOptions({ path: { desktop_id: desktopId }, throwOnError: true })
    )
})

const openDesktopInfoModal = (desktopId: string) => {
  fetchDesktopDetails(desktopId)
  showDesktopInfoModal.value = true
}

const networksModalDesktop = ref<VideowallDesktop | null>(null)
const viewerDesktopId = ref<string | null>(null)
const viewerLayout = ref<ViewerLayout>('single')
// The wall stays mounted under the viewer: pause its previews.
provide(
  PREVIEWS_PAUSED_INJECTION_KEY,
  computed(() => viewerDesktopId.value !== null || viewerLayout.value === 'mosaic')
)
const shownDesktops = computed(() => groups.value.flatMap((g) => g.desktops))
const showAll = () => {
  viewerLayout.value = 'mosaic'
}
const bastionModalDesktop = ref<VideowallDesktop | null>(null)
</script>

<template>
  <PageContainer class="max-w-none gap-8">
    <div ref="headingRef" class="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-3">
      <Button
        icon="arrow-left"
        hierarchy="link-color"
        class="w-min shrink-0 whitespace-nowrap px-0"
        :as="RouterLink"
        :to="{ name: 'deployment', params: { deploymentId } }"
      >
        {{ t('layouts.single-page.go-back') }}
      </Button>
      <span class="h-8 w-px shrink-0 bg-gray-warm-300" aria-hidden="true" />
      <!-- The layout's h1 names the page. -->
      <div
        class="flex h-10 min-w-0 items-center gap-2 rounded-[10px] border border-secondary-2-300 bg-secondary-2-100 pl-2.5 pr-3.5"
      >
        <Icon name="layout-alt-04" class="shrink-0" stroke-color="secondary-2-600" />
        <Skeleton v-if="isPending" class="h-5 w-40" />
        <TruncatedText
          v-else
          as="h2"
          :title="deployment?.name ?? ''"
          class="min-w-0 text-lg font-semibold text-gray-warm-900"
        />
      </div>
      <span class="flex items-center gap-1 text-xs text-gray-warm-500">
        <Icon name="info-circle" size="xs" class="shrink-0" stroke-color="gray-warm-500" />
        {{ t('views.deployment-videowall.gpu-warning') }}
      </span>
    </div>

    <!-- A direct child of the page: sticky only holds within its parent. -->
    <div
      ref="toolbarRef"
      :class="
        cn(
          'sticky top-16 z-40 -mx-5 -mt-8 -mb-3 border-b border-transparent bg-base-background px-5 py-3',
          // A shadow would fall on the desktop group heading stuck right below: a line instead.
          windowScrollY > 0 && (groupBy === 'desktop' ? 'border-gray-warm-200' : 'shadow-lg')
        )
      "
    >
      <PageToolbar>
        <template #view>
          <div
            v-if="!headingVisible"
            class="flex shrink-0 items-center gap-2 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-200"
          >
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  hierarchy="secondary-gray"
                  icon="arrow-left"
                  class="p-[10px] shrink-0"
                  :as="RouterLink"
                  :to="{ name: 'deployment', params: { deploymentId } }"
                  :aria-label="t('layouts.single-page.go-back')"
                />
              </TooltipTrigger>
              <TooltipContent :title="t('layouts.single-page.go-back')" side="bottom" />
            </Tooltip>
            <div
              class="flex h-10.5 max-w-60 min-w-0 items-center gap-2 rounded-[10px] border border-secondary-2-300 bg-secondary-2-100 px-2.5 max-md:hidden"
            >
              <Icon
                name="layout-alt-04"
                size="sm"
                class="shrink-0"
                stroke-color="secondary-2-600"
              />
              <span class="truncate text-sm font-semibold text-gray-warm-900">
                {{ deployment?.name }}
              </span>
            </div>
            <span class="h-8 w-px shrink-0 bg-gray-warm-300" aria-hidden="true" />
          </div>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                hierarchy="secondary-gray"
                :icon="viewMode === 'cards' ? 'rows-01' : 'grid-01'"
                class="p-[10px] shrink-0"
                :aria-label="
                  viewMode === 'cards'
                    ? t('views.deployment-videowall.view.table')
                    : t('views.deployment-videowall.view.cards')
                "
                @click="viewMode = viewMode === 'cards' ? 'table' : 'cards'"
              />
            </TooltipTrigger>
            <TooltipContent
              :title="
                viewMode === 'cards'
                  ? t('views.deployment-videowall.view.table')
                  : t('views.deployment-videowall.view.cards')
              "
              side="top"
            />
          </Tooltip>
          <Select v-model="groupBy">
            <SelectTrigger
              class="h-10.5 w-fit shrink-0 gap-2 bg-base-white"
              :aria-label="t('views.deployment-videowall.group-by.label')"
            >
              <SelectValue>
                <span v-if="selectedGroupByOption" class="inline-flex items-center gap-2">
                  <Icon :name="selectedGroupByOption.icon" size="sm" aria-hidden="true" />
                  {{ selectedGroupByOption.label }}
                </span>
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem
                v-for="option in groupByOptions"
                :key="option.value"
                :value="option.value"
              >
                <span class="inline-flex items-center gap-2">
                  <Icon :name="option.icon" size="sm" aria-hidden="true" />
                  {{ option.label }}
                </span>
              </SelectItem>
            </SelectContent>
          </Select>
        </template>
        <template #search>
          <SearchInput
            :id="VIDEOWALL_SEARCH_INPUT_ID"
            v-model="filterText"
            :placeholder="t('views.deployment-videowall.filter-placeholder')"
          />
        </template>
        <template #filters>
          <FilterTags v-model="filterTags" :categories="filterCategories" />
        </template>
        <template #actions>
          <Tooltip>
            <TooltipTrigger as-child>
              <!-- A disabled button gets no pointer events: the span keeps the tooltip. -->
              <span class="inline-flex">
                <Button
                  :icon="isStoppingAll ? 'loading-02' : 'stop'"
                  :icon-class="
                    isStoppingAll ? 'motion-safe:animate-[spin_2s_linear_infinite]' : undefined
                  "
                  hierarchy="destructive"
                  :disabled="!anyDesktopStoppable"
                  @click="openStopAllModal"
                >
                  {{ t('views.deployment.buttons.stop-all') }}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent
              v-if="!anyDesktopStoppable"
              side="top"
              :title="
                stopCounts.stopping > 0
                  ? t('views.deployment.stop-all.stopping-tooltip')
                  : t('views.deployment.stop-all.no-started-tooltip')
              "
            />
          </Tooltip>
          <Tooltip>
            <TooltipTrigger as-child>
              <!-- A disabled button gets no pointer events: the span keeps the tooltip. -->
              <span class="inline-flex">
                <Button
                  hierarchy="primary"
                  icon="tv-03"
                  :disabled="shownDesktops.length === 0"
                  @click="showAll"
                >
                  {{
                    filterSummary
                      ? t('views.deployment-videowall.review.filtered', shownDesktops.length)
                      : t('views.deployment-videowall.review.all')
                  }}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent
              :title="
                filterSummary
                  ? t('views.deployment-videowall.review.filtered-hint')
                  : t('views.deployment-videowall.review.all-hint')
              "
            />
          </Tooltip>
        </template>
      </PageToolbar>
    </div>

    <EmptyState
      v-if="!isPending && groups.length === 0"
      kind="desktops"
      variant="no-results"
      :searching="filterText.trim().length > 0"
      :active-filters="activeFilterCount"
      @clear-search="filterText = ''"
      @clear-filters="filterTags = emptyFilterTags(FILTER_CATEGORIES)"
    />

    <template v-else>
      <div
        v-if="isPending"
        class="grid gap-4"
        :style="{ gridTemplateColumns: `repeat(auto-fill, minmax(${cardMinWidth}px, 1fr))` }"
      >
        <DesktopCardSkeleton
          v-for="i in 8"
          :key="i"
          :variant="i % 2 ? 'started' : 'stopped'"
          :class="cardSize === 'md' ? 'h-[280px]' : 'h-[310px]'"
        />
      </div>

      <div
        v-else-if="viewMode === 'cards'"
        ref="cardGridRef"
        class="grid items-start gap-6 pb-3"
        :style="{ gridTemplateColumns: `repeat(${cardColumns}, minmax(0, 1fr))` }"
      >
        <!-- A group spans one column per desktop, so small groups share a row. -->
        <section
          v-for="group in groups"
          :key="group.key"
          class="flex min-w-0 flex-col gap-3"
          :style="{ gridColumn: `span ${Math.min(group.desktops.length, cardColumns)}` }"
        >
          <!-- A desktop group runs long: its heading stays under the toolbar. -->
          <header
            :class="
              cn(
                'flex min-w-0 items-center gap-2.5 border-b border-gray-warm-200 pb-2',
                groupBy === 'desktop' && 'sticky z-30 -mt-2 bg-base-background pt-2'
              )
            "
            :style="groupBy === 'desktop' ? { top: groupHeaderTop } : undefined"
          >
            <template v-if="groupBy === 'user'">
              <Avatar size="sm">
                <AvatarImage :src="group.photo ?? ''" :alt="group.label" />
                <AvatarFallback>{{ initials(group.label) }}</AvatarFallback>
              </Avatar>
              <TruncatedText
                as="h2"
                :title="group.label"
                class="min-w-0 text-md font-semibold text-gray-warm-900"
              />
            </template>
            <div
              v-else
              class="flex min-w-0 items-center gap-1.5 rounded-lg border border-gray-warm-200 bg-base-white px-2.5 py-1"
            >
              <Icon name="monitor-02" size="sm" stroke-color="gray-warm-500" />
              <TruncatedText
                as="h2"
                :title="group.label"
                class="min-w-0 text-md font-semibold text-gray-warm-900"
              />
            </div>
            <span class="flex shrink-0 items-center gap-1.5 text-sm text-gray-warm-500">
              {{ t('views.deployment-videowall.group-count', group.desktops.length) }}
              <template v-for="status in GROUP_STATUSES" :key="status.key">
                <template v-if="groupStatuses.get(group.key)![status.key] > 0">
                  <span aria-hidden="true">·</span>
                  <span :class="cn('size-2 rounded-full', status.dot)" />
                  {{
                    t(
                      `views.deployment-videowall.group-status.${status.key}`,
                      groupStatuses.get(group.key)![status.key]
                    )
                  }}
                </template>
              </template>
            </span>
          </header>

          <div
            class="grid gap-4"
            :style="{
              gridTemplateColumns: `repeat(${Math.min(group.desktops.length, cardColumns)}, minmax(0, 1fr))`
            }"
          >
            <div
              v-for="dktp in group.desktops"
              :key="dktp.id"
              class="flex min-w-0 flex-col gap-1.5"
            >
              <!-- Every card of a desktop group shares one name: say whose it is. -->
              <AvatarLabel
                v-if="groupBy === 'desktop'"
                :src="dktp.user_photo"
                :name="dktp.user_name"
                size="xs"
                class="min-w-0 [&>div]:min-w-0"
                name-class="truncate text-sm font-medium text-gray-warm-600"
              >
                <template #name>
                  <TruncatedText as="span" :title="dktp.user_name" class="block" />
                </template>
              </AvatarLabel>
              <DesktopCard
                v-model:overlay="cardOverlays[dktp.id]"
                :size="cardSize"
                fill
                :desktop="dktp"
                :preferred-viewer="preferedViewers[dktp.id]"
                @desktop-start="startDesktop({ path: { desktop_id: dktp.id } })"
                @desktop-stop="stopDesktop({ path: { desktop_id: dktp.id } })"
                @open-viewer="(viewer) => fetchAndOpenViewer({ desktopId: dktp.id, viewer })"
                @show-info-modal="openDesktopInfoModal(dktp.id)"
                @show-networks-modal="networksModalDesktop = dktp"
                @show-bastion-modal="bastionModalDesktop = dktp"
              >
                <template #header-actions>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <!-- A disabled button gets no pointer events: the span keeps the tooltip. -->
                      <span class="inline-flex">
                        <Button
                          hierarchy="link-gray"
                          size="sm"
                          :class="
                            cn(overlayIconButtonClass(false, cardSize), 'disabled:opacity-40')
                          "
                          icon="maximize-02"
                          icon-stroke-color="base-white"
                          :disabled="!canViewInBrowser(dktp)"
                          :aria-label="t('components.desktops.desktop-card.actions.expand')"
                          @click="viewerDesktopId = dktp.id"
                        />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent
                      :title="
                        canViewInBrowser(dktp)
                          ? t('components.desktops.desktop-card.actions.expand')
                          : t('views.view-deployment.sections.viewer.empty.not-available')
                      "
                    />
                  </Tooltip>
                </template>
              </DesktopCard>
            </div>
          </div>
        </section>
      </div>

      <div v-else class="flex flex-col gap-4 pb-3">
        <section v-for="group in tableGroups" :key="group.key" class="flex flex-col gap-2">
          <header v-if="groupBy === 'desktop'" class="flex items-center gap-2">
            <div
              class="flex min-w-0 items-center gap-1.5 rounded-lg border border-gray-warm-200 bg-base-white px-2 py-0.5"
            >
              <Icon name="monitor-02" size="xs" stroke-color="gray-warm-500" />
              <h2 class="text-sm font-semibold text-gray-warm-900">{{ group.label }}</h2>
            </div>
            <span class="text-xs text-gray-warm-500">
              {{ t('views.deployment-videowall.group-count', group.desktops.length) }}
            </span>
          </header>
          <DesktopsDataTable
            :desktops="group.desktops"
            :prefered-viewers="preferedViewers"
            show-user
            :can-expand="canViewInBrowser"
            @expand="(dktp) => (viewerDesktopId = dktp.id)"
            @desktop-start="(dktp) => startDesktop({ path: { desktop_id: dktp.id } })"
            @desktop-stop="(dktp) => stopDesktop({ path: { desktop_id: dktp.id } })"
            @open-viewer="
              (data) => fetchAndOpenViewer({ desktopId: data.dktp.id, viewer: data.viewer })
            "
            @show-info-modal="(dktp) => openDesktopInfoModal(dktp.id)"
            @show-networks-modal="(dktp) => (networksModalDesktop = dktp as VideowallDesktop)"
            @show-bastion-modal="(dktp) => (bastionModalDesktop = dktp as VideowallDesktop)"
          />
        </section>
      </div>
    </template>
  </PageContainer>

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
    :interfaces="desktopDetails?.interfaces"
    :viewers="desktopDetails?.viewers"
    :isos="desktopDetails?.isos?.map((iso) => iso.name)"
    :floppies="desktopDetails?.floppies?.map((floppy) => floppy.name)"
    :reservables="desktopDetails?.reservables?.vgpus"
    :kind="'desktop'"
    :template="desktopDetails?.template"
    desktop-kind="deployment"
    @close="
      () => {
        showDesktopInfoModal = false
        resetDesktopDetails()
      }
    "
  />

  <DesktopNetworksModal
    v-if="networksModalDesktop !== null"
    :open="networksModalDesktop !== null"
    :desktop-id="networksModalDesktop.id"
    :desktop-name="networksModalDesktop.name"
    :desktop-ip="networksModalDesktop.ip"
    :desktop-status="networksModalDesktop.status"
    desktop-kind="deployment"
    @close="networksModalDesktop = null"
  />

  <DesktopBastionInfoModal
    v-if="bastionModalDesktop !== null"
    :open="bastionModalDesktop !== null"
    :desktop-id="bastionModalDesktop.id"
    :desktop-name="bastionModalDesktop.name"
    @close="bastionModalDesktop = null"
  />

  <VideowallViewerModal
    v-model="viewerDesktopId"
    v-model:layout="viewerLayout"
    :desktops="shownDesktops"
    :deployment-name="deployment?.name ?? ''"
    :total="allDesktops.length"
    :filter-summary="filterSummary"
    @clear-filters="clearFilters"
  />

  <StopAllDesktopsModal
    :open="showStopAllModal"
    :started-count="stopCounts.started"
    :shutting-down-count="stopCounts.shuttingDown"
    :pending="stopAllIsPending"
    :error="stopAllError"
    @close="closeStopAllModal"
    @confirm="confirmStopAll"
  />
</template>
