<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'

import { getDeploymentOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { DeploymentUserDetail } from '@/gen/oas/apiv4'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/badge'
import { Icon } from '@/components/icon'
import { Skeleton } from '@/components/ui/skeleton'
import { AvatarLabel } from '@/components/avatar-label'
import { DataTable } from '@/components/data-table'
import type { HeaderCell } from '@/components/data-table/DataTable.vue'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { TruncatedText } from '@/components/truncated-text'
import { EmptyState, PageContainer, PageToolbar, SearchInput } from '@/components/page'
import { toast } from '@/components/ui/toast'

import { VisibilityLegend, VisibilityToggle } from '@/components/deployments/visibility'
import { DeploymentVisibilityModal } from '@/components/deployments/actions/visibility-modal'
import { useDeploymentVisibility } from '@/composables/useDeploymentVisibility'
import {
  cellFor,
  columnCells,
  columnState,
  deploymentState,
  desktopColumns,
  isRunning,
  rowState,
  runningCount,
  userDesktops,
  visibleCount,
  type MatrixDesktop,
  type DesktopColumn
} from '@/lib/deployment-visibility'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const deploymentId = computed(() => route.params.deploymentId as string)

const {
  data: deploymentEntry,
  isPending,
  isError
} = useQuery(getDeploymentOptions({ path: { deployment_id: deploymentId.value } }))

watch(isError, (failed) => {
  if (failed) router.replace({ name: 'deployments' })
})

const info = computed(() => deploymentEntry.value?.info)
const users = computed(() => deploymentEntry.value?.users ?? [])
const columns = computed(() => desktopColumns(info.value?.desktops ?? []))

const allCells = computed(() => users.value.flatMap(userDesktops))
const masterState = computed(() => deploymentState(users.value, !!info.value?.tag_visible))

const { mutate: setVisibility, isPending: isSettingVisibility } = useDeploymentVisibility(
  () => deploymentId.value
)

// ─── Filtering ─────────────────────────────────────────────────────────

const inputSearch = ref('')
const stateFilter = ref<'all' | 'visible' | 'hidden' | 'mixed'>('all')
const SEARCH_INPUT_ID = 'deployment-visibility-search'

const stateFilterOptions = computed(() => [
  { value: 'all', label: t('views.deployment-visibility.filter.all') },
  { value: 'visible', label: t('views.deployment-visibility.filter.visible') },
  { value: 'hidden', label: t('views.deployment-visibility.filter.hidden') },
  { value: 'mixed', label: t('views.deployment-visibility.filter.mixed') }
])

const filteredUsers = computed(() =>
  users.value.filter((user) => {
    const term = inputSearch.value.trim().toLowerCase()
    if (term && !user.name.toLowerCase().includes(term)) return false
    if (stateFilter.value === 'all') return true
    const state = rowState(user)
    if (stateFilter.value === 'visible') return state === true
    if (stateFilter.value === 'hidden') return state === false
    return state === 'indeterminate'
  })
)

const hasFilters = computed(() => !!inputSearch.value.trim() || stateFilter.value !== 'all')

// ─── Table ─────────────────────────────────────────────────────────────

const header = computed<HeaderCell[]>(() => [
  {
    name: t('views.deployment-visibility.headers.user'),
    key: 'name',
    sortable: true,
    sticky: 'left',
    // DataTableHead is `h-10` by default, so this cell would keep a fixed 40px
    // and sit at the top of a header row the desktop columns make taller.
    // Bottom-padded so the label lands on the desktop columns' sub-label line:
    // the header's own 8px, the inner block's 8px, the 24px toggle and its 6px gap.
    headerClass: 'h-auto min-h-28 py-2 items-end pb-[46px]',
    // Elastic so the matrix keeps the same width whatever the deployment holds:
    // whatever the capped desktop columns leave over lands here.
    width: 'minmax(200px, 1fr)'
  },
  {
    name: t('views.deployment-visibility.headers.all'),
    key: 'all',
    sortable: false,
    width: '88px',
    headerClass: 'h-auto min-h-28 py-2 justify-center items-end pb-[46px]',
    cellClass: 'justify-center'
  },
  ...columns.value.map((column) => ({
    name: column.name,
    key: column.key,
    sortable: false,
    // Ceiling so one desktop does not stretch its column across the page: the
    // columns measure the same whether the deployment has one or a dozen. The
    // floor keeps a two-line name readable; the tooltip carries the full one.
    width: 'minmax(200px, 360px)',
    headerClass:
      'h-auto min-h-28 py-2 justify-center items-stretch overflow-visible border-l border-gray-warm-200',
    cellClass: 'justify-center border-l border-gray-warm-200'
  }))
])

/** "2/3" under each column header, so nobody has to count checkboxes. */
const columnCount = (tagDesktopId: string | null) => {
  const cells = columnCells(users.value, tagDesktopId)
  return `${visibleCount(cells)}/${cells.length}`
}

// ─── Applying changes ──────────────────────────────────────────────────

const VISIBILITY_TOAST_ID = 'deployment-visibility'

interface VisibilityAction {
  visible: boolean
  affected: MatrixDesktop[]
  users?: string[]
  tagDesktopIds?: string[]
  /** Success toast. */
  message: string
  /** Names the scope in the confirmation. */
  title: string
  /** The master switch reaches every user, so it confirms even with nothing started. */
  alwaysConfirm?: boolean
}

/** Held while the confirmation is open, applied with the answer to it. */
const pendingAction = ref<VisibilityAction | null>(null)
const pendingRunning = computed(() =>
  pendingAction.value ? runningCount(pendingAction.value.affected) : 0
)

/**
 * Hiding a started desktop pulls it from under whoever is using it, so that
 * case asks first whether to stop it too. Showing never interrupts anyone.
 */
function requestVisibility(action: VisibilityAction) {
  if (!action.affected.length) return
  if (action.alwaysConfirm || (!action.visible && runningCount(action.affected))) {
    pendingAction.value = action
    return
  }
  applyVisibility(action, false)
}

function confirmPending(stopStartedDomains: boolean) {
  const action = pendingAction.value
  pendingAction.value = null
  if (action) applyVisibility(action, stopStartedDomains)
}

function applyVisibility(action: VisibilityAction, stopStartedDomains: boolean) {
  const { affected } = action

  // Snapshot the exact prior partition. Undoing with the inverse rectangle
  // would be wrong whenever the prior state was mixed: re-hiding a column
  // that had 3 of 12 visible would hide all 12.
  const wasVisible = affected.filter((desktop) => desktop.visible).map((d) => d.desktop_id)
  const wasHidden = affected.filter((desktop) => !desktop.visible).map((d) => d.desktop_id)

  const undo = () => {
    if (wasVisible.length) {
      setVisibility({
        path: { deployment_id: deploymentId.value },
        body: { visible: true, desktop_ids: wasVisible }
      })
    }
    if (wasHidden.length) {
      setVisibility({
        path: { deployment_id: deploymentId.value },
        body: { visible: false, desktop_ids: wasHidden }
      })
    }
  }

  setVisibility(
    {
      path: { deployment_id: deploymentId.value },
      body: {
        visible: action.visible,
        users: action.users ?? null,
        tag_desktop_ids: action.tagDesktopIds ?? null,
        stop_started_domains: stopStartedDomains
      }
    },
    {
      onSuccess: () => {
        toast.success(action.message, {
          // One shared id: a new change replaces the previous toast in place
          // and restarts its countdown, instead of stacking toasts where only
          // the newest counts down and Undo is ambiguous.
          id: VISIBILITY_TOAST_ID,
          // Required: an actioned toast is sticky by default.
          duration: 8000,
          // Undo restores visibility, and nothing can restore a stopped
          // desktop, so a hide that stopped desktops is not offered as undoable.
          action: stopStartedDomains
            ? undefined
            : { label: t('common.actions.undo'), onClick: undo }
        })
      },
      onError: () => toast.error(t('views.deployment.visibility.toast.error'))
    }
  )
}

// Which way a click goes. The tooltips read the direction from here rather
// than recomputing it, so they cannot disagree with what the click does. An
// aggregate toggle shows everything unless all of it is already visible, so
// a mixed column or row turns visible.
const columnWillShow = (column: DesktopColumn) =>
  columnState(users.value, column.tagDesktopId) !== true

const rowWillShow = (user: DeploymentUserDetail) => rowState(user) !== true

const cellWillShow = (user: DeploymentUserDetail, column: DesktopColumn) =>
  !cellFor(user, column.tagDesktopId)?.visible

// The sentence that names the click, shared by the tooltip and the title of
// the confirmation, so the modal cannot describe a different change.
const columnTitle = (column: DesktopColumn, visible: boolean) =>
  t(
    visible ? 'views.deployment.visibility.column-show' : 'views.deployment.visibility.column-hide',
    { desktop: column.name }
  )

const userTitle = (user: DeploymentUserDetail, visible: boolean) =>
  t(visible ? 'views.deployment.visibility.row-show' : 'views.deployment.visibility.row-hide', {
    user: user.name
  })

const cellTitle = (user: DeploymentUserDetail, column: DesktopColumn, visible: boolean) =>
  t(visible ? 'views.deployment.visibility.cell-show' : 'views.deployment.visibility.cell-hide', {
    desktop: column.name,
    user: user.name
  })

/** Names the click, not the options: on a mixed column the icon cannot say it. */
const columnTooltip = (column: DesktopColumn) =>
  `${columnTitle(column, columnWillShow(column))} — ${t('views.deployment.visibility.all-users-warning')}`

const cellTooltip = (user: DeploymentUserDetail, column: DesktopColumn) =>
  cellTitle(user, column, cellWillShow(user, column))

/** Stable accessible name; a disabled row still says why it is inert, like
 *  the empty cells do, because a disabled control never reaches its tooltip. */
const rowLabel = (user: DeploymentUserDetail) =>
  userDesktops(user).length
    ? t('views.deployment.visibility.row-label', { user: user.name })
    : t('views.deployment.visibility.no-desktops-user', { user: user.name })

/** A row with no desktops explains why it is inert, like the cells do. */
const rowTooltip = (user: DeploymentUserDetail) =>
  userDesktops(user).length
    ? userTitle(user, rowWillShow(user))
    : t('views.deployment.visibility.no-desktops-user', { user: user.name })

function toggleColumn(column: DesktopColumn) {
  const visible = columnWillShow(column)
  requestVisibility({
    visible,
    affected: columnCells(users.value, column.tagDesktopId),
    tagDesktopIds: column.tagDesktopId ? [column.tagDesktopId] : undefined,
    title: columnTitle(column, visible),
    message: t(
      visible
        ? 'views.deployment.visibility.toast.shown.desktop'
        : 'views.deployment.visibility.toast.hidden.desktop',
      { desktop: column.name }
    )
  })
}

function toggleUser(user: DeploymentUserDetail) {
  const visible = rowWillShow(user)
  requestVisibility({
    visible,
    affected: userDesktops(user),
    users: [user.id],
    title: userTitle(user, visible),
    message: t(
      visible
        ? 'views.deployment.visibility.toast.shown.user'
        : 'views.deployment.visibility.toast.hidden.user',
      { user: user.name }
    )
  })
}

function toggleCell(user: DeploymentUserDetail, column: DesktopColumn) {
  const desktop = cellFor(user, column.tagDesktopId)
  if (!desktop) return
  const visible = cellWillShow(user, column)
  requestVisibility({
    visible,
    affected: [desktop],
    users: [user.id],
    tagDesktopIds: column.tagDesktopId ? [column.tagDesktopId] : undefined,
    title: cellTitle(user, column, visible),
    message: t(
      visible
        ? 'views.deployment.visibility.toast.shown.cell'
        : 'views.deployment.visibility.toast.hidden.cell',
      { desktop: column.name, user: user.name }
    )
  })
}

// Both directions confirm: applying to every user of the deployment at once
// is worth a deliberate step, whatever is started.
function toggleAll(visible: boolean) {
  requestVisibility({
    visible,
    affected: allCells.value,
    alwaysConfirm: true,
    title: t(
      visible
        ? 'views.deployment.visibility.confirm.deployment-show-title'
        : 'views.deployment.visibility.confirm.deployment-hide-title',
      { deployment: info.value?.name ?? '' }
    ),
    message: t(
      visible
        ? 'views.deployment.visibility.toast.shown.deployment'
        : 'views.deployment.visibility.toast.hidden.deployment'
    )
  })
}

const goBack = () =>
  router.push({ name: 'deployment', params: { deploymentId: deploymentId.value } })
</script>

<template>
  <DeploymentVisibilityModal
    v-if="pendingAction"
    open
    :action="pendingAction.visible ? 'show' : 'hide'"
    :title="pendingAction.title"
    :running-count="pendingRunning"
    @confirm="confirmPending"
    @close="pendingAction = null"
  />

  <PageContainer>
    <Button icon="arrow-left" hierarchy="link-color" class="w-min -mx-4" @click="goBack">
      {{ t('views.deployment-visibility.back') }}
    </Button>

    <div
      class="flex flex-col gap-4 rounded-lg border border-base-border bg-base-banner p-4 px-6 sm:flex-row sm:items-center sm:justify-between"
    >
      <div class="flex flex-col gap-2">
        <div class="flex items-center gap-2">
          <Icon name="eye" size="md" stroke-color="gray-warm-600" />
          <Skeleton v-if="isPending" class="h-5 w-40" />
          <TruncatedText
            v-else
            as="h2"
            :title="info?.name ?? ''"
            class="max-w-120 text-lg font-bold"
          />
          <Badge
            v-if="masterState === 'indeterminate'"
            color="lightyellow"
            icon="minus"
            shape="square"
            :content="t('views.deployments.visibility.mixed')"
          />
          <Badge
            v-else-if="masterState"
            color="blue"
            icon="eye"
            shape="square"
            :content="t('views.deployments.visibility.visible')"
          />
          <Badge
            v-else
            color="gray"
            icon="eye-off"
            shape="square"
            :content="t('views.deployments.visibility.hidden')"
          />
        </div>
        <p class="text-sm text-gray-warm-600">
          {{
            t('views.deployment-visibility.summary', {
              visible: visibleCount(allCells),
              total: allCells.length
            })
          }}
        </p>
      </div>

      <div class="flex shrink-0 gap-2">
        <Button
          hierarchy="secondary-gray"
          icon="eye"
          size="sm"
          :disabled="isSettingVisibility || masterState === true"
          @click="toggleAll(true)"
        >
          {{ t('views.deployment-visibility.show-all') }}
        </Button>
        <Button
          hierarchy="secondary-gray"
          icon="eye-off"
          size="sm"
          :disabled="isSettingVisibility || masterState === false"
          @click="toggleAll(false)"
        >
          {{ t('views.deployment-visibility.hide-all') }}
        </Button>
      </div>
    </div>

    <PageToolbar>
      <template #search>
        <SearchInput
          :id="SEARCH_INPUT_ID"
          v-model="inputSearch"
          :placeholder="t('views.deployment-visibility.search-placeholder')"
        />
      </template>
      <template #filters>
        <Select v-model="stateFilter">
          <SelectTrigger class="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              v-for="option in stateFilterOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </SelectItem>
          </SelectContent>
        </Select>
      </template>
    </PageToolbar>

    <div v-if="isPending" class="flex flex-col gap-4">
      <Skeleton v-for="n in 4" :key="'skeleton-' + n" class="h-16 w-full rounded-r-2xl" />
    </div>

    <template v-else-if="filteredUsers.length > 0">
      <!-- Grouped with the table so PageContainer's gap-6 does not push the
           legend away from it. -->
      <div class="flex flex-col gap-2">
        <div class="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
          <VisibilityLegend />
          <!-- The toggles are boxed icons, so say out loud that they are ours to click. -->
          <p class="flex items-center gap-1.5 pr-2 text-xs text-gray-warm-500">
            <Icon
              name="cursor-click-01"
              size="xs"
              stroke-color="gray-warm-500"
              aria-hidden="true"
            />
            {{ t('views.deployment-visibility.click-hint') }}
          </p>
        </div>
        <DataTable
          :rows="filteredUsers"
          :headers="header"
          cell-class="h-16"
          row-class="group"
          :is-clickable="false"
        >
          <!-- A column header applies to every user of the deployment,
               including those on other pages of the table. -->
          <template v-for="column in columns" :key="column.key" #[`head-${column.key}`]>
            <!-- Title at the top, controls pinned to the bottom, so every
                 column's title and toggle share a line across the table. -->
            <div class="flex h-full w-full flex-col items-center justify-between gap-3 py-2">
              <!-- `px-2`: a two-line name would otherwise run into the rules
                   that separate one desktop from the next. Clamped at two
                   lines, so only a longer name gets the tooltip. -->
              <TruncatedText
                as="span"
                :lines="2"
                :title="column.name"
                class="max-w-full px-2 text-center text-xs font-medium"
              />
              <!-- Same tracks as every cell below, so the divider and the
                   two sub-columns line up down the whole table. -->
              <div class="grid w-full grid-cols-2">
                <span class="flex flex-col items-center gap-1.5">
                  <!-- Label and count on one line: stacked they cost a row of
                       header height and squeeze the title above them. -->
                  <span
                    class="flex items-baseline gap-1 text-[10px] leading-3 tracking-wide text-gray-warm-500 uppercase"
                  >
                    {{ t('views.deployments.visibility.visible') }}
                    <span class="text-xs normal-case">{{ columnCount(column.tagDesktopId) }}</span>
                  </span>
                  <!-- Only the toggle carries the warning: on the whole header
                       it fired over the title too and read as a column hint. -->
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <VisibilityToggle
                        :model-value="columnState(users, column.tagDesktopId)"
                        :disabled="isSettingVisibility"
                        :label="
                          t('views.deployment.visibility.column-label', { desktop: column.name })
                        "
                        @update:model-value="toggleColumn(column)"
                      />
                    </TooltipTrigger>
                    <TooltipContent :title="columnTooltip(column)" />
                  </Tooltip>
                </span>
                <span class="flex flex-col items-center self-stretch">
                  <span class="text-[10px] leading-3 tracking-wide text-gray-warm-500 uppercase">
                    {{ t('views.deployment-visibility.headers.state') }}
                  </span>
                </span>
              </div>
            </div>
          </template>

          <template #cell-name="{ row }">
            <AvatarLabel :src="row.photo" :name="row.name" />
          </template>

          <template #cell-all="{ row }">
            <Tooltip>
              <TooltipTrigger as-child>
                <span class="inline-flex">
                  <VisibilityToggle
                    :model-value="rowState(row as DeploymentUserDetail)"
                    :disabled="
                      isSettingVisibility || !userDesktops(row as DeploymentUserDetail).length
                    "
                    :label="rowLabel(row as DeploymentUserDetail)"
                    @update:model-value="toggleUser(row as DeploymentUserDetail)"
                  />
                </span>
              </TooltipTrigger>
              <TooltipContent :title="rowTooltip(row as DeploymentUserDetail)" />
            </Tooltip>
          </template>

          <template
            v-for="column in columns"
            :key="`cell-${column.key}`"
            #[`cell-${column.key}`]="{ row }"
          >
            <!-- Visibility and run state are different things, so they get a
                 track each instead of sharing the cell around the toggle. -->
            <div class="grid w-full grid-cols-2 items-center">
              <span class="flex justify-center">
                <Tooltip v-if="!cellFor(row as DeploymentUserDetail, column.tagDesktopId)">
                  <TooltipTrigger as-child>
                    <span class="inline-flex">
                      <VisibilityToggle
                        :model-value="false"
                        disabled
                        :label="
                          t('views.deployment.visibility.no-desktop', {
                            desktop: column.name,
                            user: row.name
                          })
                        "
                      />
                    </span>
                  </TooltipTrigger>
                  <TooltipContent
                    :title="
                      t('views.deployment.visibility.no-desktop', {
                        desktop: column.name,
                        user: row.name
                      })
                    "
                  />
                </Tooltip>
                <Tooltip v-else>
                  <TooltipTrigger as-child>
                    <span class="inline-flex">
                      <VisibilityToggle
                        :model-value="
                          !!cellFor(row as DeploymentUserDetail, column.tagDesktopId)?.visible
                        "
                        :disabled="isSettingVisibility"
                        :label="
                          t('views.deployment.visibility.cell-label', {
                            desktop: column.name,
                            user: row.name
                          })
                        "
                        @update:model-value="toggleCell(row as DeploymentUserDetail, column)"
                      />
                    </span>
                  </TooltipTrigger>
                  <TooltipContent :title="cellTooltip(row as DeploymentUserDetail, column)" />
                </Tooltip>
              </span>

              <span class="flex h-full items-center justify-center">
                <!-- Running desktops are the ones hiding actually interrupts. -->
                <Tooltip v-if="cellFor(row as DeploymentUserDetail, column.tagDesktopId)">
                  <TooltipTrigger as-child>
                    <span
                      class="size-2.5 shrink-0 rounded-full"
                      :class="
                        isRunning(cellFor(row as DeploymentUserDetail, column.tagDesktopId))
                          ? 'bg-success-600 ring-2 ring-success-200'
                          : 'bg-gray-warm-300'
                      "
                    />
                  </TooltipTrigger>
                  <TooltipContent
                    :title="
                      isRunning(cellFor(row as DeploymentUserDetail, column.tagDesktopId))
                        ? t('views.deployment-visibility.legend.started')
                        : t('views.deployment-visibility.legend.stopped')
                    "
                  />
                </Tooltip>
              </span>
            </div>
          </template>
        </DataTable>
      </div>
    </template>

    <EmptyState v-else kind="deployment-users" :variant="hasFilters ? 'no-results' : 'first-run'" />
  </PageContainer>
</template>
