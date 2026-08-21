<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  getDesktopInfoOptions,
  getDesktopInfoQueryKey,
  getUserConfigOptions,
  editDesktopMutation,
  getUserDesktopsLegacyQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import DomainConfigurationPanel from '@/components/domain/DomainConfigurationPanel.vue'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  toBastionTarget,
  toDomainHardware,
  toGuestProperties,
  toImageInput,
  toReservables
} from '@/lib/domainPayload'
import router from '@/router'

const { t } = useI18n()
const route = useRoute()
const queryClient = useQueryClient()

const desktopId = computed(() => route.params.desktopId as string)

const {
  isPending: desktopLoading,
  isError: desktopLoadError,
  data: desktopData
} = useQuery({
  ...getDesktopInfoOptions({
    path: { desktop_id: desktopId.value }
  }),
  enabled: computed(() => !!desktopId.value),
  staleTime: 0,
  refetchOnMount: 'always'
})

const { data: userConfig } = useQuery(getUserConfigOptions())
const canUseBastion = computed(() => userConfig.value?.can_use_bastion === true)

// Card colour only. `DomainInfoResponse` has no persistent flag; only
// deployment desktops report a `deployment_name`.
const desktopKind = computed<'persistent' | 'nonpersistent' | 'deployment'>(() =>
  desktopData.value?.deployment_name ? 'deployment' : 'persistent'
)

const panelRef = ref<InstanceType<typeof DomainConfigurationPanel> | null>(null)
const areFormsValid = computed(() => panelRef.value?.areFormsValid ?? false)

const submitError = ref<string | null>(null)

const { mutate: submitEdit, isPending: submitPending } = useMutation({
  ...editDesktopMutation(),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: getUserDesktopsLegacyQueryKey() })
    queryClient.removeQueries({
      queryKey: getDesktopInfoQueryKey({ path: { desktop_id: desktopId.value } }),
      exact: true
    })
    router.push({ name: 'desktops' })
  },
  onError: (error) => {
    submitError.value = 'description_code' in error ? error.description_code : 'generic'
  }
})

const handleSubmit = () => {
  if (!areFormsValid.value || !panelRef.value) return
  submitError.value = null

  const data = panelRef.value.getFormData()

  submitEdit({
    path: { desktop_id: desktopId.value },
    body: {
      name: data.name,
      description: data.description,
      image: toImageInput(data.image, data.imageFile),
      guest_properties: toGuestProperties(data.access),
      hardware: toDomainHardware(data.hardware),
      reservables: toReservables(data.hardware),
      ...(canUseBastion.value ? { bastion_target: toBastionTarget(data.access?.bastion) } : {})
    }
  })
}
</script>

<template>
  <header class="flex flex-col md:flex-row items-center max-w-480 w-full mx-auto mb-8 gap-4">
    <div class="flex flex-row items-center gap-4 w-full">
      <Button
        :as="RouterLink"
        :to="{ name: 'desktops' }"
        hierarchy="link-color"
        icon="arrow-left"
        class="pb-6 pt-0 pl-0"
      >
        {{ t('views.edit-desktop.header.cancel') }}
      </Button>
    </div>
    <div class="flex flex-row items-center justify-end gap-4 w-full">
      <Button class="min-w-32" :disabled="!areFormsValid || submitPending" @click="handleSubmit">
        {{ t('views.edit-desktop.header.save') }}
      </Button>
    </div>
  </header>

  <main class="max-w-320 w-full mx-auto flex flex-col gap-[24px]">
    <Alert v-if="desktopLoadError" variant="destructive">
      <AlertTitle>{{ t('views.edit-desktop.errors.load') }}</AlertTitle>
    </Alert>
    <Alert v-if="submitError" variant="destructive">
      <AlertTitle>{{ t('views.edit-desktop.errors.title') }}</AlertTitle>
      <AlertDescription>{{ t(`api.edit-desktop.errors.${submitError}`) }}</AlertDescription>
    </Alert>

    <DomainConfigurationPanel
      ref="panelRef"
      :desktop-id="desktopId"
      :loading="desktopLoading"
      :info="desktopData"
      :kind="desktopKind"
      :image="desktopData?.image ?? undefined"
      :image-domain-id="desktopId"
      :image-persist-on-save="false"
      always-show-configuration
      :show-bastion-config="canUseBastion"
      context="edit-desktop"
    />
  </main>
</template>
