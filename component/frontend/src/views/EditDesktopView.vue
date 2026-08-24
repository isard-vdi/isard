<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { FormHeader } from '@/components/form-header'
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

const formHeaderRef = ref<InstanceType<typeof FormHeader> | null>(null)
const panelRef = ref<InstanceType<typeof DomainConfigurationPanel> | null>(null)
const areFormsValid = computed(() => panelRef.value?.areFormsValid ?? false)

const isTouched = computed(() => panelRef.value?.isDirty ?? false)

const submitError = ref<string | null>(null)

const { mutate: submitEdit, isPending: submitPending } = useMutation({
  ...editDesktopMutation(),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: getUserDesktopsLegacyQueryKey() })
    queryClient.removeQueries({
      queryKey: getDesktopInfoQueryKey({ path: { desktop_id: desktopId.value } }),
      exact: true
    })
    formHeaderRef.value?.allowLeave()
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
  <FormHeader
    ref="formHeaderRef"
    :cancel-to="{ name: 'desktops' }"
    :cancel-label="t('components.form-header.cancel-edit')"
    :confirm-cancel="isTouched"
    :next-label="t('views.edit-desktop.header.save')"
    :next-disabled="!areFormsValid"
    :next-pending="submitPending"
    @next="handleSubmit"
  />

  <main class="max-w-320 w-full mx-auto flex flex-col gap-6">
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
