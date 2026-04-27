<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import { ArrowLeft, Info, LayoutGrid, Maximize } from 'lucide-vue-next'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'

import { getDeploymentVideowallOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import NoVNC from '@/components/noVNC/NoVNC.vue'
import DeploymentVideowallCard from '@/components/deployment-videowall/DeploymentVideowallCard.vue'
import {
  VIDEOWALL_ALIVE_STATES,
  type VideowallDeployment,
  type VideowallDesktop
} from '@/components/deployment-videowall/types'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const deploymentId = computed(() => route.params.deploymentId as string)

const { data, isPending } = useQuery(
  getDeploymentVideowallOptions({
    path: { deployment_id: deploymentId.value }
  })
)

// The apiv4 endpoint has no Pydantic response model so codegen typed the
// payload as `unknown`. The contract is whatever
// CommonDeployments.get_deployment(id, desktops=True) returns, which is the
// same shape the vue 2 videowall consumes today.
const deployment = computed<VideowallDeployment | undefined>(
  () => data.value as VideowallDeployment | undefined
)

const viewMode = ref<'grid' | 'single'>('grid')
const selectedDesktopId = ref<string | null>(null)
const filterText = ref('')
const showStartedOnly = ref(false)

const desktops = computed<VideowallDesktop[]>(() => {
  const all = deployment.value?.desktops ?? []
  // Sort tiles with a live viewer to the front so the grid leads with usable
  // previews. Stable comparator: viewer-bearing items rank first.
  const sorted = [...all].sort((a, b) => Number(!!b.viewer) - Number(!!a.viewer))
  const started = showStartedOnly.value
    ? sorted.filter((d) => VIDEOWALL_ALIVE_STATES.has((d.state ?? '').toLowerCase()))
    : sorted
  const needle = filterText.value.toLowerCase()
  return needle ? started.filter((d) => d.userName.toLowerCase().includes(needle)) : started
})

const selectedDesktop = computed<VideowallDesktop | null>(
  () => deployment.value?.desktops.find((d) => d.id === selectedDesktopId.value) ?? null
)

// First load: pre-select the first desktop, mirroring vue 2 parity.
watch(
  () => deployment.value?.desktops?.[0]?.id,
  (firstId) => {
    if (firstId && !selectedDesktopId.value) selectedDesktopId.value = firstId
  },
  { immediate: true }
)

function selectDesktop(id: string) {
  selectedDesktopId.value = id
  viewMode.value = 'single'
}

function backToDeployment() {
  router.push({ name: 'deployment', params: { deploymentId: deploymentId.value } })
}
</script>

<template>
  <div class="container mx-auto p-4 space-y-4">
    <div class="flex items-center justify-between gap-4">
      <h1 class="text-xl font-semibold truncate">
        {{ deployment?.name ?? '' }}
      </h1>
      <div class="flex items-center gap-2">
        <Input
          v-model="filterText"
          :placeholder="t('views.deployment-videowall.filter-placeholder')"
          class="w-56"
        />
        <label class="flex items-center gap-2 text-sm">
          <Checkbox v-model:checked="showStartedOnly" />
          {{ t('views.deployment-videowall.only-started') }}
        </label>
        <Button
          variant="ghost"
          size="icon"
          :aria-label="t('views.deployment-videowall.view.grid')"
          :disabled="viewMode === 'grid'"
          @click="viewMode = 'grid'"
        >
          <LayoutGrid class="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          :aria-label="t('views.deployment-videowall.view.single')"
          :disabled="viewMode === 'single' || !selectedDesktopId"
          @click="viewMode = 'single'"
        >
          <Maximize class="h-4 w-4" />
        </Button>
        <Button variant="outline" @click="backToDeployment">
          <ArrowLeft class="h-4 w-4 mr-2" />
          {{ t('views.deployment-videowall.back-to-deployment') }}
        </Button>
      </div>
    </div>

    <div
      class="flex items-start gap-2 rounded border border-blue-200 bg-blue-50 text-blue-900 p-3 text-sm"
    >
      <Info class="h-4 w-4 mt-0.5 shrink-0" />
      <span>{{ t('views.deployment-videowall.gpu-warning') }}</span>
    </div>

    <div
      v-if="isPending"
      class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
    >
      <Skeleton v-for="i in 8" :key="i" class="h-[244px] w-full rounded-lg" />
    </div>

    <div
      v-else-if="viewMode === 'grid'"
      class="overflow-y-auto pb-3"
      style="height: calc(100vh - 200px)"
    >
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <DeploymentVideowallCard
          v-for="d in desktops"
          :key="d.id"
          :desktop="d"
          @select="selectDesktop(d.id)"
        />
      </div>
    </div>

    <div v-else>
      <h2 class="text-lg font-semibold mb-2">
        {{ selectedDesktop?.userName }} - {{ deployment?.desktopName }}
      </h2>
      <NoVNC
        v-if="selectedDesktop?.viewer"
        :viewer="selectedDesktop.viewer.values"
        height="750px"
        :quality-level="6"
      />
      <div
        v-else
        class="flex flex-col items-center justify-center bg-base-black"
        style="height: 750px"
      >
        <div
          class="rounded-full"
          style="
            width: 70px;
            height: 70px;
            opacity: 0.5;
            background: #d5d5cd url(/api/v4/logo) center / 70px 70px no-repeat;
          "
        />
        <p class="text-base-white text-center mt-2">
          {{ t('views.deployment-videowall.desktop-not-available') }}
        </p>
      </div>
    </div>
  </div>
</template>
