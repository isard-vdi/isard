<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'

import { useQuery, useMutation } from '@tanstack/vue-query'
import { getUserDesktopsOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { getDesktopDetails } from '@/gen/oas/apiv4'
import { checkQuotaNewTemplateOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { QuotaExceededModal } from '@/components/modal'
import { QUOTA_STALE_TIME } from '@/lib/constants'

import { DesktopCellImage, DesktopCellName } from '@/components/desktops-data-table'
import { Button } from '@/components/ui/button'
import { copyToClipboard } from '@/lib/utils'
import { resolveDesktopKind } from '@/lib/desktops'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { DomainInfoModal } from '@/components/desktops'
import { StepperForm, type StepperFormStep } from '@/components/stepper-form'
import { FormHeader } from '@/components/form-header'
import NewTemplateForm from '@/components/templates/new-template-form/NewTemplateForm.vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import DatatablePagination from '@/components/ui/data-table-pagination/DatatablePagination.vue'
import {
  DataTableBackground,
  DataTable,
  DataTableBody,
  DataTableCell,
  DataTableHeaderRow,
  DataTableRow,
  DataTableHead,
  DataTableEmpty
} from '@/components/ui/data-table'

import type { ColumnDef, SortingState } from '@tanstack/vue-table'
import {
  useVueTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  getFilteredRowModel
} from '@tanstack/vue-table'

import { cn, valueUpdater } from '@/lib/utils'
import { EmptyState, SearchInput } from '@/components/page'

const route = useRoute()
const router = useRouter()
const { t, d } = useI18n()

// --------------------------------------------------
// Quota check
// --------------------------------------------------

const quotaQuery = useQuery({
  ...checkQuotaNewTemplateOptions(),
  staleTime: QUOTA_STALE_TIME,
  retry: false
})

const quotaCheckPassed = computed(() => quotaQuery.isSuccess.value)

// --------------------------------------------------

const {
  isPending: desktopsIsPending,
  isError: desktopsIsError,
  error: desktopsError,
  data: desktops
} = useQuery({
  ...getUserDesktopsOptions(),
  enabled: computed(() => {
    return !route.params.desktopId
  })
})

// ------------------------------------------

const showDesktopInfoModal = ref(false)
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
    const { data } = await getDesktopDetails({
      path: {
        desktop_id: desktopId
      },
      throwOnError: true
    })
    return data
  }
})

const openDesktopInfoModal = (desktopId: string) => {
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

// ------------------------------------------

const headers = [
  {
    key: 'photo',
    name: '',
    width: 'min-content'
  },
  {
    key: 'name',
    name: t('components.desktops.data-table.headers.name'),
    sortable: true,

    width: 'minmax(var(--spacing-48), var(--spacing-96))'
  },
  {
    key: 'description',
    name: t('components.desktops.data-table.headers.description'),
    sortable: true
  },
  {
    key: 'actions',
    name: '',
    width: 'min-content'
  }
]

const currentStep = ref(route.params.desktopId ? 2 : 1)

const steps = computed<StepperFormStep[]>(() => [
  {
    step: 1,
    title: t('views.new-template.stepper-steps.select-desktop')
  },
  {
    step: 2,
    title: t('views.new-template.stepper-steps.configure-template')
  }
])

const goToPreviousStep = () => {
  if (currentStep.value > 1) {
    currentStep.value -= 1
  }
}

const goToNextStep = () => {
  if (currentStep.value < steps.value.length) {
    currentStep.value += 1
  }
}

// if step changes to 2 and no selectedDesktopId, go back to step 1
watch(currentStep, (newStep) => {
  if (newStep === 2 && !selectedDesktopId.value) {
    currentStep.value = 1
  }
})

const selectedDesktopId = ref<string | null>((route.params.desktopId as string) || null)

const handleRowClick = (row: any) => {
  if (row.status === DesktopStatusEnum.STOPPED) {
    selectedDesktopId.value = selectedDesktopId.value === row.id ? null : row.id
  }
}

const formHeaderRef = ref<InstanceType<typeof FormHeader> | null>(null)
const newTemplateFormRef = ref<InstanceType<typeof NewTemplateForm> | null>(null)

const handleTemplateCreated = (templateId: string) => {
  formHeaderRef.value?.allowLeave()
  router.push({ name: 'templates', params: { templateId } })
}

const pageSize = computed(() => 10)

const sorting = ref<SortingState>([])

const globalFilter = ref('')

const tableData = computed(
  () =>
    desktops.value?.desktops.filter((desktop) => desktop.type === 'persistent' && !desktop.tag) ||
    []
)

const table = useVueTable({
  get data() {
    return tableData.value
  },
  get columns() {
    return headers.map((header) => ({
      accessorKey: header.key,
      header: header.name
    }))
  },
  getCoreRowModel: getCoreRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
  initialState: {
    pagination: {
      pageSize: pageSize.value,
      pageIndex: 0
    }
  },
  getSortedRowModel: getSortedRowModel(),
  onSortingChange: (updaterOrValue) => valueUpdater(updaterOrValue, sorting),
  getFilteredRowModel: getFilteredRowModel(),

  onGlobalFilterChange: (updaterOrValue) => valueUpdater(updaterOrValue, globalFilter),
  state: {
    get sorting() {
      return sorting.value
    },
    get globalFilter() {
      return globalFilter.value
    }
  },
  autoResetAll: false
})

const NEW_TEMPLATE_SEARCH_INPUT_ID = 'new-template-search'
</script>

<template>
  <!-- Quota Exceeded Modal -->
  <QuotaExceededModal
    :open="quotaQuery.isError.value"
    :title="t('components.templates.quota-exceeded-modal.title')"
    :description="t('components.templates.quota-exceeded-modal.description')"
    :cancel-label="t('components.templates.quota-exceeded-modal.cancel')"
    :cancel-to="{ name: 'templates' }"
  />

  <template v-if="quotaCheckPassed">
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

    <FormHeader
      ref="formHeaderRef"
      :cancel-to="route.params.desktopId ? { name: 'desktops' } : { name: 'templates' }"
      :confirm-cancel="!!newTemplateFormRef?.isDirty"
      :show-previous="!route.params.desktopId && currentStep > 1"
      @previous="goToPreviousStep"
    >
      <template v-if="!route.params.desktopId" #stepper>
        <div class="shrink-0 w-80">
          <StepperForm v-model="currentStep" :steps="steps" />
        </div>
      </template>

      <template #next>
        <template v-if="currentStep === 2">
          <Button
            class="min-w-32"
            type="submit"
            :disabled="!newTemplateFormRef?.isValid || newTemplateFormRef?.isPending"
            :icon="newTemplateFormRef?.isPending ? 'loading-02' : ''"
            icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
            @click="newTemplateFormRef?.handleSubmit()"
            >{{ t('views.new-template.header.create-template') }}</Button
          >
        </template>
        <Button v-else class="min-w-32" :disabled="!selectedDesktopId" @click="goToNextStep">
          {{ t('views.new-template.header.next') }}
        </Button>
      </template>
    </FormHeader>

    <main class="max-w-320 w-full mx-auto flex flex-col gap-6">
      <template v-if="currentStep === 1">
        <div class="flex flex-col md:flex-row items-center justify-between gap-2">
          <h1 class="text-lg font-semibold text-gray-warm-900 line-clamp-2">
            {{ t('views.new-template.select.title') }}
          </h1>

          <SearchInput
            :id="NEW_TEMPLATE_SEARCH_INPUT_ID"
            v-model="globalFilter"
            class="min-w-48"
            :placeholder="t('views.desktops.filters.search.placeholder')"
          />
        </div>

        <DataTableBackground>
          <DataTable
            :template-cols="
              headers.map((header) => header.width || 'minmax(var(--spacing-48), 1fr)')
            "
          >
            <DataTableHeaderRow>
              <DataTableHead
                v-for="(header, index) in headers"
                :key="'header-' + index"
                :sortable="header.sortable"
                :sorted="table.getColumn(header.key)?.getIsSorted()"
                @togle-sorting="table.getColumn(header.key)?.toggleSorting()"
              >
                {{ header.name }}
              </DataTableHead>
            </DataTableHeaderRow>

            <DataTableBody>
              <template v-if="table.getRowModel().rows?.length">
                <DataTableRow
                  v-for="row in table.getPaginationRowModel().rows"
                  :key="row.id"
                  class="cursor-pointer"
                  :class="{
                    'bg-brand-100 hover:bg-brand-200':
                      row.original.id && row.original.id === selectedDesktopId,
                    'cursor-not-allowed *:opacity-50':
                      row.original.status !== DesktopStatusEnum.STOPPED
                  }"
                  tabindex="0"
                  @click="handleRowClick(row.original)"
                  @keydown.enter="handleRowClick(row.original)"
                  @keydown.space.prevent="handleRowClick(row.original)"
                >
                  <DataTableCell>
                    <div class="flex flex-row items-center gap-2">
                      <DesktopCellImage
                        :desktop="row.original"
                        @copy-to-clipboard="copyToClipboard"
                      />
                    </div>
                  </DataTableCell>

                  <DataTableCell>
                    <DesktopCellName
                      :desktop-name="row.original.name"
                      :notification-text="
                        row.original.status === DesktopStatusEnum.STOPPED
                          ? null
                          : t('views.new-template.select.desktop-not-stopped')
                      "
                      notification-text-color="error-600"
                      notification-icon-color="currentColor"
                    />
                  </DataTableCell>

                  <DataTableCell>
                    <p class="text-sm text-muted-foreground line-clamp-3">
                      {{ row.original.description }}
                    </p>
                  </DataTableCell>

                  <DataTableCell>
                    <div class="flex flex-row items-center justify-end gap-2">
                      <Tooltip>
                        <TooltipTrigger as-child>
                          <Button
                            hierarchy="secondary-gray"
                            icon="info-circle"
                            class="aspect-square p-[10px]"
                            @click.stop="openDesktopInfoModal(row.original.id)"
                            @keydown.space.stop
                            @keydown.enter.stop
                          />
                        </TooltipTrigger>
                        <TooltipContent
                          :title="t('components.desktops.desktop-card.actions.info')"
                        />
                      </Tooltip>
                    </div>
                  </DataTableCell>
                </DataTableRow>
              </template>

              <DataTableEmpty v-else>
                <!-- No eligible desktop at all is a different dead end than a
                     search that matched none of them. -->
                <EmptyState
                  v-if="tableData.length === 0"
                  variant="no-results"
                  :title="t('components.empty.template-sources.title')"
                  :description="t('components.empty.template-sources.description')"
                >
                  <template #actions>
                    <Button
                      hierarchy="secondary-gray"
                      icon="monitor-04"
                      @click="router.push({ name: 'desktops' })"
                    >
                      {{ t('views.desktops.go-to-desktops') }}
                    </Button>
                  </template>
                </EmptyState>
                <EmptyState
                  v-else
                  variant="no-results"
                  searching
                  @clear-search="globalFilter = ''"
                />
              </DataTableEmpty>
            </DataTableBody>
          </DataTable>

          <template #pagination>
            <DatatablePagination :table="table"> </DatatablePagination>
          </template>
        </DataTableBackground>
      </template>
      <template v-else-if="currentStep === 2">
        <Alert v-if="!selectedDesktopId" variant="destructive" class="max-w-256 w-full mx-auto">
          <FeaturedIconOutline kind="outline" color="error" />

          <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
            'errors.no-selected-desktop.title'
          }}</AlertTitle>
          <AlertDescription>{{ 'errors.no-selected-desktop.description' }}</AlertDescription>
        </Alert>

        <NewTemplateForm
          v-else
          ref="newTemplateFormRef"
          :desktop-id="selectedDesktopId"
          @template-created="handleTemplateCreated"
        />
      </template>
    </main>
  </template>
</template>
