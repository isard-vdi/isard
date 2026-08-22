<script setup lang="ts">
import { useQuery, useMutation } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  getAllSharedDeploymentsOptions,
  getUserDetailsOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { getDeploymentUserDesktopsDetail } from '@/gen/oas/apiv4/'
import { type SharedDeployment } from '@/gen/oas/apiv4'
import type { DomainInfoItem } from '@/components/desktops'
import { DesktopCardBaseStacked, DesktopCardHeader } from '@/components/desktop-card'
import { type CardSize } from '@/components/desktop-card'
import { useWindowSize } from '@vueuse/core'
import { Button } from '@/components/ui/button'
import { useI18n } from 'vue-i18n'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { DesktopCardSkeleton } from '@/components/desktop-card'
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import desktopsEmptyImg from '@/assets/img/desktops-empty.svg'
import templatesEmptyImg from '@/assets/img/templates-empty.svg'
import { AvatarLabel } from '@/components/avatar-label'
import { DomainInfoModal } from '@/components/desktops'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  FilterPanel,
  FilterToggle,
  PageContainer,
  PageToolbar,
  SearchInput
} from '@/components/page'
import { useFilterPanel } from '@/composables/useFilterPanel'

const { t } = useI18n()

const {
  isPending: deploymentsArePending,
  isError: deploymentsIsError,
  error: deploymentsError,
  data: deployments
} = useQuery(getAllSharedDeploymentsOptions())

const {
  mutate: fetchAndOpenDeploymentDesktopsModal,
  data: deploymentDesktops,
  reset: resetDeploymentDesktops
} = useMutation({
  mutationFn: async ({ deploymentId, userId }: { deploymentId: string; userId: string }) => {
    const { data } = await getDeploymentUserDesktopsDetail({
      path: {
        deployment_id: deploymentId,
        user_id: userId
      },
      throwOnError: true
    })
    return data
  },
  onSuccess: () => {
    showDeploymentInfoModal.value = true
  }
})

const { data: user } = useQuery(getUserDetailsOptions())

const { width: windowWidth } = useWindowSize()

const cardSize = computed<CardSize>(() => {
  if (windowWidth.value < 1280) return 'md'
  return 'lg'
})

const cardGridMinWidth = computed(() => (cardSize.value === 'md' ? '250px' : '412px'))

// Filters
interface DeploymentFilters {
  status: 'all' | 'started'
}

const deploymentFilters = ref<DeploymentFilters>({ status: 'all' })

const showDeploymentFilters = useFilterPanel('shared_deployments_filters_state')

// Search has its own always-visible input; only the ones the panel hides count.
const activeDeploymentFilterCount = computed(() =>
  deploymentFilters.value.status === 'all' ? 0 : 1
)

// Filtered deployments
const filteredDeployments = computed(() => {
  const allDeployments = deployments.value?.deployments ?? []
  return allDeployments.filter(areDeploymentsVisible)
})

// Visibility
const areDeploymentsVisible = (deployment: SharedDeployment) => {
  //  Search filter
  const matchesSearch =
    inputSearch.value.toLowerCase() === '' ||
    deployment.name.toLowerCase().includes(inputSearch.value.toLowerCase()) ||
    deployment.description?.toLowerCase().includes(inputSearch.value.toLowerCase())

  // Visibility filter
  const matchesVisibility =
    deploymentFilters.value.status === 'all' ||
    (deploymentFilters.value.status === 'started' && deployment.started_desktops > 0)

  return matchesSearch && matchesVisibility
}

const inputSearch = ref<string>('')

const emptyState = computed(() => {
  const isSearching = inputSearch.value.length > 0

  return {
    title: isSearching
      ? t('components.empty-search.title')
      : t('components.empty.title', { kind: t('domains.deployments', 0) }),
    image: isSearching ? templatesEmptyImg : desktopsEmptyImg,
    styles: isSearching ? 'md:flex-row-reverse mt-16' : ''
  }
})

// Deployment desktops info
const showDeploymentInfoModal = ref(false)

const deploymentDesktopItems = computed<DomainInfoItem[]>(() => {
  if (!deploymentDesktops.value) return []
  return deploymentDesktops.value.map((d) => ({
    domainId: d.id,
    name: d.name,
    description: d.description,
    ip: d.ip,
    status: d.status,
    vcpu: d.vcpu,
    ram: d.memory,
    bootOrder: d.boot_order.map((bo) => bo.name),
    diskBus: d.disk_bus?.name,
    vga: d.videos.map((v) => v.name),
    viewers: d.viewers,
    fullscreen: d.fullscreen,
    isos: d.isos?.map((iso) => iso.name),
    floppies: d.floppies?.map((f) => f.name),
    reservables: d.reservables?.vgpus,
    credentials: d.credentials,
    kind: 'desktop' as const,
    template: d.template,
    desktopKind: 'deployment' as const
  }))
})

const handleNotImplemented = () => alert('not implemented yet')

const SHARED_DEPLOYMENTS_SEARCH_INPUT_ID = 'shared-deployments-search'
</script>

<template>
  <PageContainer>
    <PageToolbar>
      <template #search>
        <SearchInput
          :id="SHARED_DEPLOYMENTS_SEARCH_INPUT_ID"
          v-model="inputSearch"
          :placeholder="t('views.deployments.filters.search.placeholder')"
        />
      </template>
      <template #filters>
        <FilterToggle v-model="showDeploymentFilters" :active-count="activeDeploymentFilterCount" />
      </template>
      <template #panel>
        <FilterPanel :open="showDeploymentFilters">
          <ToggleGroup
            v-model="deploymentFilters.status"
            :spacing="1"
            type="single"
            size="default"
            class="bg-base-white border border-1-5 border-gray-warm-300 p-1 rounded-lg"
          >
            <ToggleGroupItem value="all" variant="gray-warm">
              <span>{{ t('views.deployments.filters.status.all') }}</span>
            </ToggleGroupItem>
            <ToggleGroupItem value="started" variant="gray-warm">
              <span>{{ t('views.deployments.filters.status.started') }}</span>
            </ToggleGroupItem>
          </ToggleGroup>
        </FilterPanel>
      </template>
    </PageToolbar>
    <div class="w-full">
      <div
        v-if="deploymentsArePending"
        class="grid gap-4 w-full"
        :style="{ gridTemplateColumns: `repeat(auto-fill, minmax(${cardGridMinWidth}, 1fr))` }"
      >
        <DesktopCardSkeleton variant="started" class="h-[310px]" />
        <DesktopCardSkeleton variant="stopped" class="h-[310px]" />
      </div>
      <p v-else-if="deploymentsIsError" class="bg-error-100 text-error-800 p-4 rounded-md">
        {{ t('views.shared-deployments.error.loading') }} {{ deploymentsError }}
      </p>
      <div
        v-else-if="filteredDeployments.length > 0"
        class="grid gap-6 w-full"
        :style="{ gridTemplateColumns: `repeat(auto-fill, minmax(${cardGridMinWidth}, 1fr))` }"
      >
        <template v-for="deployment in filteredDeployments" :key="deployment.id">
          <DesktopCardBaseStacked
            desktop-kind="deployment"
            :image-url="deployment.image.url || ''"
            fill
          >
            <template #header-actions>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button
                    hierarchy="link-gray"
                    size="sm"
                    class="w-9! h-9! flex align-center justify-center bg-base-black/30 hover:bg-base-black/50 p-0! backdrop-blur-[4px]"
                    icon="info-circle"
                    icon-stroke-color="base-white"
                    @click="
                      user?.id &&
                      fetchAndOpenDeploymentDesktopsModal({
                        deploymentId: deployment.id,
                        userId: user.id
                      })
                    "
                  />
                </TooltipTrigger>
                <TooltipContent :title="t('components.desktops.desktop-card.actions.info')" />
              </Tooltip>
            </template>
            <template #header>
              <div class="truncate">
                <AvatarLabel
                  :src="deployment.user.photo || ''"
                  :name="deployment.user.name || ''"
                  name-class="inline-flex items-center p-1.5 rounded-sm font-bold text-start text-base-white bg-[#131313]/40 max-w-full w-max backdrop-blur-[4px] gap-1.5 h-6 text-[11px]"
                />
              </div>
              <DesktopCardHeader
                :name="deployment.name"
                :description="deployment.description || ''"
              />
            </template>
            <template #footer>
              <Button
                icon="arrow-circle-broken-right"
                hierarchy="secondary-color"
                size="sm"
                class="shrink-0"
                :as="RouterLink"
                :to="{
                  name: 'view-deployment',
                  params: { deploymentId: deployment.id }
                }"
              >
                {{ t('views.deployment.buttons.enter') }}
              </Button>
            </template>
          </DesktopCardBaseStacked>
        </template>
      </div>
      <template v-else>
        <Empty :class="emptyState.styles">
          <EmptyHeader>
            <EmptyMedia variant="default" class="select-none pointer-events-none">
              <img :src="emptyState.image" />
            </EmptyMedia>
          </EmptyHeader>
          <EmptyTitle class="text-[30px] font-bold">
            {{ emptyState.title }}
          </EmptyTitle>
        </Empty>
      </template>
    </div>
    <DomainInfoModal
      :open="showDeploymentInfoModal"
      :items="deploymentDesktopItems"
      kind="desktop"
      @close="
        () => {
          showDeploymentInfoModal = false
          resetDeploymentDesktops()
        }
      "
    />
  </PageContainer>
</template>
