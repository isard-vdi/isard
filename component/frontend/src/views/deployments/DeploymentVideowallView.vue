<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { useElementSize, useLocalStorage, useWindowSize } from '@vueuse/core'
import { ArrowLeft, Info } from 'lucide-vue-next'

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
import { DesktopCard, type CardSize, type OverlayKind } from '@/components/desktop-card'
import { DesktopsDataTable } from '@/components/desktops-data-table'
import {
  DesktopBastionInfoModal,
  DesktopNetworksModal,
  DomainInfoModal
} from '@/components/desktops'
import { EmptyState, PageContainer, PageToolbar, SearchInput } from '@/components/page'
import { TruncatedText } from '@/components/truncated-text'
import { useFetchAndOpenViewer } from '@/composables/useFetchAndOpenViewer'
import {
  countVideowallStatuses,
  groupVideowallDesktops,
  isRunning,
  toVideowallDesktop,
  videowallDesktopKey,
  type VideowallDesktop,
  type VideowallGroupBy
} from '@/lib/videowall'
import { cn } from '@/lib/utils'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const queryClient = useQueryClient()

const deploymentId = computed(() => route.params.deploymentId as string)

const { data: deployment, isPending } = useQuery(
  getDeploymentVideowallOptions({
    path: { deployment_id: deploymentId.value }
  })
)

const viewMode = useLocalStorage<'cards' | 'table'>('videowall-view-mode', 'cards')
const groupBy = useLocalStorage<VideowallGroupBy>('videowall-group-by', 'user')
const groupByOptions = computed<{ value: VideowallGroupBy; label: string }[]>(() => [
  { value: 'user', label: t('views.deployment-videowall.group-by.user') },
  { value: 'desktop', label: t('views.deployment-videowall.group-by.desktop') }
])
const groupByLabel = computed(
  () => groupByOptions.value.find((option) => option.value === groupBy.value)?.label ?? ''
)
const VIDEOWALL_SEARCH_INPUT_ID = 'deployment-videowall-search'
const filterText = ref('')

const FILTER_CATEGORIES = ['status', 'desktop']
const filterTags = ref(emptyFilterTags(FILTER_CATEGORIES))

const allDesktops = computed(() => (deployment.value?.desktops ?? []).map(toVideowallDesktop))

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
// Past four columns the previews get too small to read.
const MAX_CARD_COLUMNS = 4
const cardColumns = computed(() =>
  Math.min(
    MAX_CARD_COLUMNS,
    Math.max(1, Math.floor((cardGridWidth.value + CARD_GAP) / (cardMinWidth.value + CARD_GAP)))
  )
)

// A table per user would hold one or two rows each: one table, ordered by user.
const tableGroups = computed(() =>
  groupBy.value === 'user'
    ? [{ key: 'all', label: '', desktops: groups.value.flatMap((g) => g.desktops) }]
    : groups.value
)

const { mutate: startDesktop } = useMutation(startDesktopMutation())
const { mutate: stopDesktop } = useMutation(stopDesktopMutation())
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
const bastionModalDesktop = ref<VideowallDesktop | null>(null)

function backToDeployment() {
  router.push({ name: 'deployment', params: { deploymentId: deploymentId.value } })
}
</script>

<template>
  <PageContainer class="max-w-none gap-4">
    <div class="flex flex-col gap-3">
      <div class="flex items-center justify-between gap-4">
        <div class="flex min-w-0 items-baseline gap-4">
          <TruncatedText as="h1" :title="deployment?.name ?? ''" class="text-xl font-semibold" />
          <span class="flex shrink-0 items-center gap-1 text-xs text-gray-warm-500">
            <Info class="h-3.5 w-3.5" />
            {{ t('views.deployment-videowall.gpu-warning') }}
          </span>
        </div>
        <Button variant="outline" @click="backToDeployment">
          <ArrowLeft class="h-4 w-4 mr-2" />
          {{ t('views.deployment-videowall.back-to-deployment') }}
        </Button>
      </div>

      <PageToolbar>
        <template #view>
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
              class="w-52 shrink-0 bg-base-white"
              :aria-label="t('views.deployment-videowall.group-by.label')"
            >
              <SelectValue>{{ groupByLabel }}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem
                v-for="option in groupByOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
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
      </PageToolbar>
    </div>

    <div
      v-if="isPending"
      class="grid gap-4"
      :style="{ gridTemplateColumns: `repeat(auto-fill, minmax(${cardMinWidth}px, 1fr))` }"
    >
      <Skeleton
        v-for="i in 8"
        :key="i"
        :class="[cardSize === 'md' ? 'h-[280px]' : 'h-[310px]', 'w-full rounded-lg']"
      />
    </div>

    <EmptyState
      v-else-if="groups.length === 0"
      kind="desktops"
      variant="no-results"
      :searching="filterText.trim().length > 0"
      :active-filters="activeFilterCount"
      @clear-search="filterText = ''"
      @clear-filters="filterTags = emptyFilterTags(FILTER_CATEGORIES)"
    />

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
        <header class="flex min-w-0 items-center gap-2.5 border-b border-gray-warm-200 pb-2">
          <Avatar v-if="groupBy === 'user'" size="sm">
            <AvatarImage :src="group.photo ?? ''" :alt="group.label" />
            <AvatarFallback>{{ initials(group.label) }}</AvatarFallback>
          </Avatar>
          <span
            v-else
            class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-secondary-2-100"
          >
            <Icon name="layout-alt-04" size="sm" stroke-color="secondary-2-600" />
          </span>
          <TruncatedText
            as="h2"
            :title="group.label"
            class="min-w-0 text-md font-semibold text-gray-warm-900"
          />
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
          <div v-for="dktp in group.desktops" :key="dktp.id" class="flex min-w-0 flex-col gap-1.5">
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
            />
          </div>
        </div>
      </section>
    </div>

    <div v-else class="flex flex-col gap-4 pb-3">
      <section v-for="group in tableGroups" :key="group.key" class="flex flex-col gap-2">
        <header v-if="groupBy === 'desktop'" class="flex h-6 items-center gap-2">
          <h2 class="text-sm font-semibold text-gray-warm-900">{{ group.label }}</h2>
          <span class="text-xs text-gray-warm-500">
            {{ t('views.deployment-videowall.group-count', group.desktops.length) }}
          </span>
        </header>
        <DesktopsDataTable
          :desktops="group.desktops"
          :prefered-viewers="preferedViewers"
          show-user
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
</template>
