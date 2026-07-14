<script setup lang="ts">
import { ref, computed, reactive, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { z } from 'zod'
import { useForm } from '@tanstack/vue-form'

import {
  getDesktopInfoOptions,
  getDesktopInfoQueryKey,
  getUserConfigOptions,
  editDesktopMutation,
  getUserDesktopsLegacyQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import DomainHardwareForm from '@/components/domain/DomainHardwareForm.vue'
import DomainAccessForm from '@/components/domain/DomainAccessForm.vue'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/input-field'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
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
  enabled: computed(() => !!desktopId.value)
})

const { data: userConfig } = useQuery(getUserConfigOptions())
const canUseBastion = computed(() => userConfig.value?.can_use_bastion === true)

const desktopInfoFormSchema = z.object({
  name: z.string().min(4).max(50),
  description: z.string().max(255).optional()
})

const defaultValues = reactive({
  name: '',
  description: ''
})

const desktopInfoForm = useForm({
  defaultValues,
  validators: {
    onChange: desktopInfoFormSchema
  }
})

const infoValid = desktopInfoForm.useStore((state) => state.isValid)

watch(
  desktopData,
  (data) => {
    if (!data) return
    desktopInfoForm.setFieldValue('name', data.name)
    desktopInfoForm.setFieldValue('description', data.description || '')
  },
  { immediate: true }
)

const accessFormRef = ref<{
  getFormData: () => Record<string, unknown>
  isValid: boolean
} | null>(null)
const hardwareFormRef = ref<{
  getFormData: () => Record<string, unknown>
  isValid: boolean
  limitedFields: Record<string, unknown> | null
  addInterface: (ifaceId: string) => boolean | undefined
  removeInterface: (ifaceId: string) => void
  interfaces: string[]
} | null>(null)

const hardwareInterfaces = computed<string[]>(() => hardwareFormRef.value?.interfaces ?? [])

function handleAddInterfaceFromAccessForm(ifaceId: string) {
  return hardwareFormRef.value?.addInterface(ifaceId)
}
const hardwareFormIsValid = computed(() => hardwareFormRef.value?.isValid ?? true)
const accessFormIsValid = computed(() => accessFormRef.value?.isValid ?? true)

const areFormsValid = computed(
  () => infoValid.value && hardwareFormIsValid.value && accessFormIsValid.value
)

const submitError = ref<string | null>(null)

const { mutate: submitEdit, isPending: submitPending } = useMutation({
  ...editDesktopMutation(),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: getUserDesktopsLegacyQueryKey() })
    queryClient.invalidateQueries({
      queryKey: getDesktopInfoQueryKey({ path: { desktop_id: desktopId.value } })
    })
    router.push({ name: 'desktops' })
  },
  onError: (error) => {
    submitError.value = 'description_code' in error ? error.description_code : 'submit'
  }
})

interface BastionFormHttp {
  enabled?: boolean
  httpPort: number
  httpsPort: number
  proxyProtocol?: boolean
}
interface BastionFormSsh {
  enabled?: boolean
  sshPort: number
  authorizedKeys: string
}
interface BastionFormData {
  http?: BastionFormHttp | null
  ssh?: BastionFormSsh | null
}

// BastionConfigForm reports disabled protocols as `null`, but the API only
// disables a protocol when it receives an explicit `enabled: false` payload
// (a missing/null value means "leave as is"), so both branches must always
// send a full object.
function toBastionTarget(bastion: BastionFormData | undefined) {
  if (!bastion) return undefined

  return {
    http: {
      enabled: !!bastion.http?.enabled,
      http_port: bastion.http?.httpPort ?? 80,
      https_port: bastion.http?.httpsPort ?? 443,
      proxy_protocol: !!bastion.http?.proxyProtocol
    },
    ssh: {
      enabled: !!bastion.ssh?.enabled,
      port: bastion.ssh?.sshPort ?? 22,
      authorized_keys: (bastion.ssh?.authorizedKeys ?? '')
        .split('\n')
        .map((key) => key.trim())
        .filter((key) => key.length > 0)
    }
  }
}

const handleSubmit = () => {
  if (!areFormsValid.value) return
  submitError.value = null

  const accessSettings = accessFormRef.value?.getFormData() as Record<string, unknown> | undefined
  const hardwareSettings = hardwareFormRef.value?.getFormData() as
    | Record<string, unknown>
    | undefined

  submitEdit({
    path: { desktop_id: desktopId.value },
    body: {
      name: desktopInfoForm.getFieldValue('name'),
      description: desktopInfoForm.getFieldValue('description'),
      guest_properties: {
        credentials: accessSettings?.credentials,
        fullscreen: accessSettings?.fullscreen,
        viewers: accessSettings?.viewers
      },
      hardware: {
        vcpus: hardwareSettings?.vcpus,
        memory: hardwareSettings?.memory,
        disk_bus: hardwareSettings?.diskBus,
        videos: [hardwareSettings?.videos],
        boot_order: [hardwareSettings?.bootOrder],
        interfaces: hardwareSettings?.interfaces,
        isos: hardwareSettings?.isos,
        floppies: hardwareSettings?.floppies
      },
      reservables: hardwareSettings?.reservables as { vgpus?: string[] } | undefined,
      ...(canUseBastion.value
        ? { bastion_target: toBastionTarget(accessSettings?.bastion as BastionFormData) }
        : {})
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
      <AlertTitle>{{ t('views.edit-desktop.errors.submit') }}</AlertTitle>
      <AlertDescription>{{ submitError }}</AlertDescription>
    </Alert>

    <template v-if="desktopLoading">
      <Skeleton class="w-full h-40" />
      <Skeleton class="w-full h-40" />
    </template>
    <template v-else-if="desktopData">
      <section>
        <h3 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.edit-desktop.sections.info.title') }}
        </h3>
        <p class="text-sm font-regular mb-6">
          {{ t('views.edit-desktop.sections.info.description') }}
        </p>
        <div class="flex flex-col gap-3">
          <desktopInfoForm.Field v-slot="{ field }" name="name">
            <InputField
              :id="field.name"
              :name="field.name"
              :model-value="field.state.value"
              maxlength="50"
              @update:model-value="(value) => field.handleChange(String(value))"
              @input="field.handleChange(String(($event.target as HTMLInputElement).value))"
              @blur="field.handleBlur"
            />
          </desktopInfoForm.Field>
          <desktopInfoForm.Field v-slot="{ field }" name="description">
            <Textarea
              :model-value="field.state.value"
              maxlength="255"
              class="bg-base-white resize-none"
              @update:model-value="(value) => field.handleChange(String(value))"
            />
          </desktopInfoForm.Field>
        </div>
      </section>

      <section>
        <h3 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.edit-desktop.sections.access.title') }}
        </h3>
        <p class="text-sm font-regular mb-6">
          {{ t('views.edit-desktop.sections.access.description') }}
        </p>
        <DomainAccessForm
          ref="accessFormRef"
          :desktop-id="desktopId"
          :show-bastion-config="canUseBastion"
          :hardware-interfaces="hardwareInterfaces"
          :on-request-add-interface="handleAddInterfaceFromAccessForm"
        />
      </section>

      <section>
        <h3 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.edit-desktop.sections.hardware.title') }}
        </h3>
        <p class="text-sm font-regular mb-6">
          {{ t('views.edit-desktop.sections.hardware.description') }}
        </p>
        <DomainHardwareForm ref="hardwareFormRef" :desktop-id="desktopId" />
      </section>
    </template>
  </main>
</template>
