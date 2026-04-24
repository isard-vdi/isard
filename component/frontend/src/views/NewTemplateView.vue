<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'

import { useQuery, useMutation } from '@tanstack/vue-query'
import { getUserDesktopsApiV4ItemsDesktopsGetOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { getDesktopInfoApiV4ItemDesktopDesktopIdGetDetailsGet } from '@/gen/oas/apiv4'
import { checkQuotaNewTemplateOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { QuotaExceededModal } from '@/components/modal'
import { QUOTA_STALE_TIME } from '@/lib/constants'

import { DesktopCellImage, DesktopCellName } from '@/components/desktops-data-table'
import { Button } from '@/components/ui/button'
import { copyToClipboard } from '@/lib/utils'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { DomainInfoModal } from '@/components/desktops'
import { StepperForm } from '@/components/stepper-form'
import {
  Stepper,
  StepperDescription,
  StepperIndicator,
  StepperItem,
  StepperSeparator,
  StepperTitle,
  StepperTrigger
} from '@/components/ui/stepper'
import NewTemplateForm from '@/components/templates/new-template-form/NewTemplateForm.vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'

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
import InputField from '@/components/input-field/InputField.vue'

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
  ...getUserDesktopsApiV4ItemsDesktopsGetOptions(),
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
    const { data } = await getDesktopInfoApiV4ItemDesktopDesktopIdGetDetailsGet({
      path: {
        desktop_id: desktopId
      },
      throwOnError: true
    })
    return data
  },
  onSuccess: (data) => {
    showDesktopInfoModal.value = true
  }
})

const openDesktopInfoModal = async (desktopId: string) => {
  fetchDesktopDetails(desktopId)
  showDesktopInfoModal.value = true
}

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

const newTemplateFormRef = ref<InstanceType<typeof NewTemplateForm> | null>(null)

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
      :open="desktopDetails !== undefined"
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
      @close="resetDesktopDetails()"
    />

    <header
      v-if="route.params.desktopId"
      class="flex flex-col-reverse md:flex-row items-start justify-between max-w-480 w-full mx-auto mb-8 gap-4"
    >
      <div class="flex flex-col gap-1">
        <h1 class="text-lg font-bold text-gray-warm-900">
          {{ t('views.new-template.form.title') }}
        </h1>
        <h2 class="text-sm font-regular text-gray-warm-700">
          {{ t('views.new-template.form.subtitle') }}
        </h2>
      </div>

      <div class="flex gap-4 md:w-auto w-full justify-end">
        <Button hierarchy="link-color" :as="RouterLink" :to="{ name: 'desktops' }">{{
          t('views.new-template.header.cancel')
        }}</Button>

        <template v-if="newTemplateFormRef">
          <newTemplateFormRef.form.Subscribe v-slot="{ isValid, isSubmitting }">
            <Button
              type="submit"
              :disabled="!isValid || newTemplateFormRef.isPending"
              :icon="isSubmitting || newTemplateFormRef.isPending ? 'loading-02' : ''"
              icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
              @click="newTemplateFormRef.form.handleSubmit"
              >{{ t('views.new-template.header.create-template') }}</Button
            >
          </newTemplateFormRef.form.Subscribe>
        </template>
        <Skeleton v-else class="w-32" />
      </div>
    </header>
    <header
      v-else
      class="flex flex-col md:flex-row items-start justify-center max-w-480 w-full mx-auto mb-8 gap-4"
    >
      <div class="flex flex-row items-center gap-4 w-full">
        <Button
          hierarchy="link-color"
          icon="arrow-left"
          :as="RouterLink"
          :to="{ name: 'templates' }"
        >
          {{ t('views.new-template.header.cancel') }}
        </Button>
      </div>

      <div class="shrink-0 w-80">
        <Stepper v-model="currentStep">
          <StepperItem :step="1">
            <div class="flex flex-col items-center gap-1.5 w-full" :class="''">
              <div class="flex items-center w-full">
                <div class="w-12 flex justify-center shrink-0">
                  <StepperTrigger>
                    <StepperIndicator>1</StepperIndicator>
                  </StepperTrigger>
                </div>
                <div class="flex-1 min-w-0">
                  <StepperSeparator />
                </div>
              </div>
              <div class="flex items-center mt-1 w-full">
                <div class="w-12 flex items-center justify-center text-center shrink-0">
                  <div class="flex flex-col items-center">
                    <StepperTitle class="text-sm font-bold whitespace-nowrap">
                      {{ t('views.new-template.stepper-steps.select-desktop') }}
                    </StepperTitle>
                  </div>
                </div>
              </div>
            </div>
          </StepperItem>
          <StepperItem :step="2" class="flex-[0_0_auto]!">
            <div class="flex flex-col items-center gap-1.5 w-auto" :class="''">
              <div class="flex items-center w-auto">
                <div class="w-12 flex justify-center shrink-0">
                  <StepperTrigger>
                    <StepperIndicator>2</StepperIndicator>
                  </StepperTrigger>
                </div>
              </div>
              <div class="flex items-center mt-1 w-auto">
                <div class="w-12 flex items-center justify-center text-center shrink-0">
                  <div class="flex flex-col items-center">
                    <StepperTitle class="text-sm font-bold whitespace-nowrap">
                      {{ t('views.new-template.stepper-steps.configure-template') }}
                    </StepperTitle>
                  </div>
                </div>
              </div>
            </div>
          </StepperItem>
        </Stepper>
      </div>

      <div class="flex flex-row items-center justify-end gap-4 w-full">
        <Button
          hierarchy="link-color"
          :disabled="currentStep <= 1"
          @click="
            () => {
              if (currentStep > 1) {
                currentStep -= 1
              }
            }
          "
        >
          {{ t('views.new-template.header.previous') }}
        </Button>

        <template v-if="currentStep === 2">
          <template v-if="newTemplateFormRef">
            <newTemplateFormRef.form.Subscribe v-slot="{ isValid, isSubmitting }">
              <Button
                class="min-w-32"
                type="submit"
                :disabled="!isValid || newTemplateFormRef.isPending"
                :icon="isSubmitting || newTemplateFormRef.isPending ? 'loading-02' : ''"
                icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
                @click="newTemplateFormRef.form.handleSubmit"
                >{{ t('views.new-template.header.create-template') }}</Button
              >
            </newTemplateFormRef.form.Subscribe>
          </template>
          <Skeleton v-else class="h-10 w-32" />
        </template>
        <Button
          v-else
          class="min-w-32"
          :disabled="!selectedDesktopId"
          @click="
            () => {
              if (currentStep < 2) {
                currentStep += 1
              }
            }
          "
        >
          {{ t('views.new-template.header.next') }}
        </Button>
      </div>
    </header>

    <main class="max-w-320 w-full mx-auto flex flex-col gap-[24px]">
      <template v-if="currentStep === 1">
        <div class="flex flex-col md:flex-row items-center justify-between gap-2">
          <h1 class="text-lg font-semibold text-gray-warm-900 line-clamp-2">
            {{ t('views.new-template.select.title') }}
          </h1>

          <InputField
            v-model="globalFilter"
            class="w-full max-w-120 min-w-48"
            icon="search-lg"
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
                      <Button
                        hierarchy="secondary-gray"
                        icon="info-circle"
                        class="aspect-square p-[10px]"
                        @click.stop="fetchDesktopDetails(row.original.id)"
                        @keydown.space.stop
                        @keydown.enter.stop
                      />
                    </div>
                  </DataTableCell>
                </DataTableRow>
              </template>

              <DataTableEmpty v-else>
                <slot name="empty">
                  {{ t('components.datatable.empty') }}
                </slot>
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
          @template-created="
            (templateId: string) => router.push({ name: 'templates', params: { templateId } })
          "
        />
      </template>
    </main>
  </template>
</template>
