<script setup lang="ts">
import { ref, computed, watch, Teleport } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  getDeploymentUserDesktopsOptions,
  getDesktopViewerByTypeOptions,
  startDesktopMutation,
  stopDesktopMutation,
  stopUserDesktopsInDeploymentMutation,
  getDesktopDetailsOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { getDeploymentUserDesktopsDetail, type UserDeploymentDesktop } from '@/gen/oas/apiv4'

import { Button } from '@/components/ui/button'
import NoVNC from '@/components/noVNC/NoVNC.vue'

import DomainSummary from '@/components/domain/DomainSummary.vue'

import { Icon } from '@/components/icon'
import { useAuthStore } from '@/stores/auth'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyContent
} from '@/components/ui/empty'
import desktopsEmptyImg from '@/assets/img/desktops-empty.svg'
import { Separator } from '@/components/ui/separator'
import DeploymentDesktopCard from '@/components/deployment-desktop-card/DeploymentDesktopCard.vue'
import { RecreateDesktopConfirmationModal } from '@/components/recreate-desktop-confirmation-modal'
import { DomainInfoModal, type DomainInfoItem } from '@/components/desktops'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'

import { useFetchAndOpenViewer } from '@/composables/useFetchAndOpenViewer'
import { desktopActionsData } from '@/lib/desktops'

const route = useRoute()

const { t } = useI18n()

const authStore = useAuthStore()

const queryClient = useQueryClient()

const { mutate: fetchAndOpenViewer } = useFetchAndOpenViewer()

const deploymentId = computed(() => route.params.deploymentId as string)
const userId = computed(() => {
  if (route.params.userId) {
    return route.params.userId as string
  }

  return authStore.user?.user_id as string
})

const { data: desktops, refetch: refetchDesktops } = useQuery(
  getDeploymentUserDesktopsOptions({
    path: {
      deployment_id: deploymentId.value,
      user_id: userId.value
    }
  })
)

const {
  mutate: fetchViewer,
  data: viewerData,
  isPending: viewerLoading,
  isError: viewerIsError,
  error: viewerError,
  variables: viewerVariables,
  reset: resetViewer
} = useMutation({
  mutationFn: async (desktopId: string) => {
    const data = await queryClient.fetchQuery(
      getDesktopViewerByTypeOptions({
        path: {
          desktop_id: desktopId,
          viewer_type: 'browser-vnc'
        },
        throwOnError: true
      })
    )
    return data
  }
})

const { data: desktopDetails, isPending: desktopDetailsIsPending } = useQuery(
  computed(() => {
    return {
      ...getDesktopDetailsOptions({
        path: {
          desktop_id: viewerVariables.value!
        }
      }),
      enabled: computed(() => !!viewerVariables.value)
    }
  })
)

const { mutate: startDesktop } = useMutation(startDesktopMutation())
const { mutate: stopDesktop } = useMutation({
  ...stopDesktopMutation(),
  onSuccess(data, variables, onMutateResult, context) {
    if (viewerVariables.value === variables.path.desktop_id) {
      resetViewer()
    }
  }
})

const { mutate: stopDesktops, isPending: stopDesktopsIsPending } = useMutation({
  ...stopUserDesktopsInDeploymentMutation(),
  onSuccess() {
    resetViewer()
  }
})

const selectedDesktop = computed(() =>
  desktops.value?.desktops.find((d) => d.id === viewerVariables.value)
)

const selectedDesktopHasViewer = computed(
  () => desktopActionsData(selectedDesktop.value?.status ?? '').viewers
)

watch(selectedDesktopHasViewer, (hasViewer) => {
  if (viewerVariables.value && !hasViewer) {
    resetViewer()
  }
})

const fullScreen = ref(false)

const desktopsPanelCollapsed = ref(false)

// Mirrors the DeploymentDesktopCard `canOpenViewer` rule so both panel modes enable the same desktops
const canViewDesktop = (desktop: UserDeploymentDesktop) =>
  !!desktopActionsData(desktop.status).viewers &&
  !!desktop.viewers?.some((viewer) => viewer.replace(/_/g, '-') === 'browser-vnc')

const collapsedDesktopTooltip = (desktop: UserDeploymentDesktop) => {
  if (viewerVariables.value === desktop.id) {
    return t('components.deployments.desktop-card.tooltips.viewing')
  }

  if (!desktopActionsData(desktop.status).viewers) {
    return t('components.deployments.desktop-card.not-available')
  }

  if (!canViewDesktop(desktop)) {
    return t('components.deployments.desktop-card.tooltips.no-web-viewer')
  }

  return t('components.deployments.desktop-card.tooltips.view')
}

const recreateDesktopModalDesktopData = ref<{
  id: string
  name: string
} | null>(null)

const showDesktopInfoModal = ref(false)
const {
  mutate: fetchDesktopDetails,
  isPending: fetchDesktopDetailsIsPending,
  isError: fetchDesktopDetailsIsError,
  error: fetchDesktopDetailsError,
  data: modalDesktopDetails,
  variables: desktopDetailsDesktopId,
  reset: resetDesktopDetails
} = useMutation({
  mutationFn: async (desktopId: string) => {
    const data = await queryClient.fetchQuery({
      ...getDesktopDetailsOptions({
        path: {
          desktop_id: desktopId
        },
        throwOnError: true
      })
    })

    return data
  }
})

const openDesktopInfoModal = async (desktopId: string) => {
  showDesktopInfoModal.value = true
  fetchDesktopDetails(desktopId)
}

const showDeploymentInfoModal = ref(false)
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
    kind: 'desktop' as const,
    template: d.template
  }))
})

const openDeploymentInfoModal = () => {
  fetchAndOpenDeploymentDesktopsModal({
    deploymentId: deploymentId.value,
    userId: userId.value
  })
}
</script>

<template>
  <DomainInfoModal
    :open="showDesktopInfoModal"
    :domain-id="desktopDetailsDesktopId"
    :name="modalDesktopDetails?.name || ''"
    :description="modalDesktopDetails?.description"
    :status="modalDesktopDetails?.status"
    :ip="modalDesktopDetails?.ip"
    :vcpu="modalDesktopDetails?.vcpu"
    :ram="modalDesktopDetails?.memory"
    :boot-order="modalDesktopDetails?.boot_order.map((bo) => bo.name)"
    :disk-bus="modalDesktopDetails?.disk_bus?.name"
    :vga="modalDesktopDetails?.videos.map((vga) => vga.name)"
    :viewers="modalDesktopDetails?.viewers"
    :isos="modalDesktopDetails?.isos?.map((iso) => iso.name)"
    :floppies="modalDesktopDetails?.floppies?.map((floppy) => floppy.name)"
    :reservables="modalDesktopDetails?.reservables?.vgpus"
    :kind="'desktop'"
    :template="modalDesktopDetails?.template"
    @close="
      () => {
        showDesktopInfoModal = false
        resetDesktopDetails()
      }
    "
  />

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

  <RecreateDesktopConfirmationModal
    :open="recreateDesktopModalDesktopData !== null"
    :desktop="recreateDesktopModalDesktopData"
    @close="recreateDesktopModalDesktopData = null"
  />

  <div
    class="grid grid-cols-1 grid-rows-[auto_1fr] gap-4 xl:gap-x-8 h-full"
    :class="fullScreen && viewerData ? 'xl:grid-cols-1' : 'xl:grid-cols-[1fr_30rem]'"
  >
    <div class="flex flex-row items-center justify-start gap-4 xl:col-start-1 xl:row-start-1">
      <Button
        hierarchy="secondary-gray"
        class="p-[10px]"
        icon="info-circle"
        @click="openDeploymentInfoModal()"
      />

      <h1 class="text-display-xs font-bold text-gray-warm-700">
        {{ desktops?.info.name }}
      </h1>

      <div v-if="viewerData" class="ml-auto flex flex-row items-center gap-4">
        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              hierarchy="secondary-gray"
              class="p-[10px]"
              icon="underscore"
              @click="resetViewer()"
            />
          </TooltipTrigger>
          <TooltipContent
            :title="t('views.view-deployment.sections.viewer.actions.close')"
            side="top"
          />
        </Tooltip>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button
              hierarchy="secondary-gray"
              class="p-[10px]"
              :icon="fullScreen ? 'minimize-02' : 'maximize-02'"
              @click="fullScreen = !fullScreen"
            />
          </TooltipTrigger>
          <TooltipContent
            :title="
              t(
                `views.view-deployment.sections.viewer.actions.${fullScreen ? 'minimize' : 'maximize'}`
              )
            "
            side="top"
          />
        </Tooltip>
        <!-- <Button hierarchy="secondary-gray" class="p-[10px]" icon="link-external-01" disabled /> -->
      </div>
    </div>

    <div
      class="flex flex-col w-full min-w-0 min-h-0 xl:col-start-1 xl:row-start-2"
      :class="{ 'order-last xl:order-none': !viewerData }"
    >
      <Empty v-if="!viewerData">
        <EmptyHeader>
          <EmptyMedia variant="default" class="select-none pointer-events-none">
            <img :src="desktopsEmptyImg" />
          </EmptyMedia>
        </EmptyHeader>
        <EmptyTitle class="text-[30px] font-bold">{{
          t('views.view-deployment.sections.viewer.empty.title')
        }}</EmptyTitle>
        <EmptyDescription class="text-[18px]!">
          {{ t('views.view-deployment.sections.viewer.empty.description') }}
        </EmptyDescription>
      </Empty>

      <NoVNC
        v-else-if="fullScreen"
        :key="fullScreen"
        :viewer="viewerData.values"
        class="h-full! w-full! rounded-lg overflow-hidden cursor-auto! mx-0 my-0"
      />

      <div v-else class="flex flex-col gap-8 min-w-0">
        <div class="relative w-full aspect-video shrink-0">
          <NoVNC
            :key="fullScreen"
            :viewer="viewerData.values"
            height="100%"
            class="absolute inset-0 rounded-lg overflow-hidden cursor-auto!"
          />

          <Empty class="absolute inset-0 -z-10">
            <EmptyHeader>
              <EmptyMedia variant="default" class="select-none pointer-events-none">
                <img :src="desktopsEmptyImg" />
              </EmptyMedia>
            </EmptyHeader>
            <EmptyTitle class="text-[30px] font-bold">{{
              t('views.view-deployment.sections.viewer.empty.not-available')
            }}</EmptyTitle>
          </Empty>
        </div>

        <DomainSummary
          :loading="desktopDetailsIsPending"
          :title="desktopDetails?.name"
          :credentials="desktopDetails?.credentials"
          :viewers="desktopDetails?.viewers"
          :fullscreen="desktopDetails?.fullscreen"
          :vcpu="desktopDetails?.vcpu"
          :memory="desktopDetails?.memory"
          :disk-bus="desktopDetails?.disk_bus?.name"
          :videos="desktopDetails?.videos?.map((video) => video.name)"
          :interfaces="desktopDetails?.interfaces?.map((iface) => iface.name)"
          :boot-order="desktopDetails?.boot_order?.map((boot) => boot.name)"
          :isos="desktopDetails?.isos?.map((iso) => iso.name)"
          :floppies="desktopDetails?.floppies?.map((floppy) => floppy.name)"
          :vgpus="desktopDetails?.reservables?.vgpus"
        />
      </div>
    </div>

    <div
      v-if="!(fullScreen && viewerData)"
      class="flex flex-col w-full gap-12 xl:col-start-2 xl:row-start-1 xl:row-span-2 xl:max-w-120 xl:h-full"
    >
      <div
        class="flex flex-col border border-gray-warm-300 bg-base-white rounded-lg gap-2 relative _h-full xl:max-h-1/2"
      >
        <div class="flex flex-row w-full items-center justify-start p-4 pb-0 gap-2">
          <h1 class="text-display-xs font-bold text-gray-warm-700 w-full line-clamp-1">
            {{ t('views.view-deployment.sections.desktops.title') }}
          </h1>

          <Button
            hierarchy="destructive"
            :icon="stopDesktopsIsPending ? 'loading-02' : 'stop'"
            :disabled="stopDesktopsIsPending"
            :icon-class="{
              'motion-safe:animate-[spin_2s_linear_infinite]': stopDesktopsIsPending
            }"
            @click="
              stopDesktops({
                path: {
                  deployment_id: deploymentId,
                  user_id: userId
                }
              })
            "
            >{{ t('views.view-deployment.sections.desktops.actions.stop-all.label') }}</Button
          >

          <Tooltip
            v-if="
              // TODO: return whether the deployment needs booking from api
              true
            "
          >
            <TooltipTrigger as-child>
              <Button
                hierarchy="secondary-gray"
                class="p-[10px]"
                icon="calendar-plus-02"
                as="a"
                :href="// TODO: update to real booking link
                `/booking/deployment/${deploymentId}`"
                target="_blank"
              />
            </TooltipTrigger>
            <TooltipContent
              :title="t('views.view-deployment.sections.desktops.actions.book.tooltip')"
              side="top"
            />
          </Tooltip>
        </div>

        <div
          v-if="!desktopsPanelCollapsed"
          class="h-full w-full flex flex-col gap-2 overflow-y-auto mb-2"
        >
          <template v-for="(desktop, index) in desktops?.desktops" :key="desktop.id">
            <DeploymentDesktopCard
              :desktop="{ ...desktop, permissions: desktops?.info.user_permissions || [] }"
              :selected="viewerVariables === desktop.id"
              @select="fetchViewer(desktop.id)"
              @desktop-start="startDesktop({ path: { desktop_id: desktop.id } })"
              @desktop-stop="
                () => {
                  stopDesktop({ path: { desktop_id: desktop.id } })
                }
              "
              @show-info-modal="openDesktopInfoModal(desktop.id)"
              @show-recreate-modal="
                recreateDesktopModalDesktopData = { id: desktop.id, name: desktop.name }
              "
              @open-viewer="(viewer) => fetchAndOpenViewer({ desktopId: desktop.id, viewer })"
            />

            <Separator v-if="index < (desktops?.desktops || []).length - 1" />
          </template>
        </div>
        <div v-else class="flex flex-row gap-4 p-4 mb-4">
          <!-- TODO: merge this into DeploymentDesktopCard to centralise the logic -->
          <template v-for="desktop in desktops?.desktops" :key="desktop.id">
            <Tooltip>
              <TooltipTrigger as-child>
                <div
                  class="size-16 shrink-0 bg-cover bg-center rounded-md relative"
                  :class="{
                    'ring-3 ring-brand-700': viewerVariables === desktop.id,
                    'cursor-pointer': viewerVariables !== desktop.id && canViewDesktop(desktop),
                    'contrast-50 cursor-not-allowed!': !canViewDesktop(desktop)
                  }"
                  :style="{
                    backgroundImage: `url(${desktop.image.url})`
                  }"
                  @click="
                    () => {
                      if (canViewDesktop(desktop) && viewerVariables !== desktop.id) {
                        fetchViewer(desktop.id)
                      }
                    }
                  "
                />
              </TooltipTrigger>
              <TooltipContent
                :title="desktop.name"
                :subtitle="collapsedDesktopTooltip(desktop)"
                side="top"
              />
            </Tooltip>
          </template>
        </div>

        <div class="absolute -bottom-8 h-16 left-0 right-0 flex items-center justify-center">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                class="p-[10px]"
                size="lg"
                :icon="desktopsPanelCollapsed ? 'chevron-down' : 'chevron-up'"
                icon-class="size-6"
                @click="desktopsPanelCollapsed = !desktopsPanelCollapsed"
              />
            </TooltipTrigger>
            <TooltipContent
              :title="
                t(
                  `views.view-deployment.sections.desktops.actions.${
                    desktopsPanelCollapsed ? 'expand' : 'collapse'
                  }`
                )
              "
              side="top"
            />
          </Tooltip>
        </div>
      </div>

      <!-- <div
        class="flex flex-col border border-gray-warm-300 bg-base-white rounded-lg gap-2 relative h-full"
      ></div> -->
    </div>
  </div>
</template>
