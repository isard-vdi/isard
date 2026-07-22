<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { useForm } from '@tanstack/vue-form'
import { z } from 'zod'

import {
  getDeploymentBastionOptions,
  getDeploymentBastionQueryKey,
  setDeploymentBastionMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { Alert, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FieldContent, FieldError, FieldLabel } from '@/components/ui/field'
import { Icon } from '@/components/icon'
import { InputField } from '@/components/input-field'
import { Modal } from '@/components/modal'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'

const { t } = useI18n()

interface Props {
  open?: boolean
  deploymentId: string
  deploymentName: string
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  close: []
}>()

const queryClient = useQueryClient()

const {
  data: bastionConfig,
  isPending,
  isError
} = useQuery(
  getDeploymentBastionOptions({
    path: { deployment_id: props.deploymentId }
  })
)

const { mutateAsync: saveBastion, isPending: isSaving } = useMutation(
  setDeploymentBastionMutation()
)

const errorMessage = ref('')

const formSchema = z.object({
  sshEnabled: z.boolean(),
  sshPort: z.number().min(1).max(65535),
  httpEnabled: z.boolean(),
  httpPort: z.number().min(1).max(65535),
  httpsPort: z.number().min(1).max(65535)
})

// Hydrate from the deployment's stored config once the query resolves.
const form = useForm({
  defaultValues: reactive({
    sshEnabled: computed(() => bastionConfig.value?.ssh?.enabled ?? false),
    sshPort: computed(() => bastionConfig.value?.ssh?.port ?? 22),
    httpEnabled: computed(() => bastionConfig.value?.http?.enabled ?? false),
    httpPort: computed(() => bastionConfig.value?.http?.http_port ?? 80),
    httpsPort: computed(() => bastionConfig.value?.http?.https_port ?? 443)
  }),
  validators: {
    onBlur: formSchema
  },
  onSubmit: async ({ value }) => {
    errorMessage.value = ''
    try {
      await saveBastion({
        path: { deployment_id: props.deploymentId },
        body: {
          ssh: { enabled: value.sshEnabled, port: value.sshPort },
          http: {
            enabled: value.httpEnabled,
            http_port: value.httpPort,
            https_port: value.httpsPort
          }
        }
      })
      queryClient.invalidateQueries({
        queryKey: getDeploymentBastionQueryKey({ path: { deployment_id: props.deploymentId } })
      })
      queryClient.invalidateQueries(['getDeployment'])
      emit('close')
    } catch {
      errorMessage.value = t('components.deployment-bastion-modal.error-saving')
    }
  }
})
</script>

<template>
  <Modal
    :open="props.open"
    show-close-button
    size="xl"
    class="pt-6"
    :title="t('components.deployment-bastion-modal.title', { name: props.deploymentName })"
    :description="t('components.deployment-bastion-modal.description')"
    @close="emit('close')"
  >
    <div class="flex flex-col gap-4 pb-2">
      <!-- Loading state -->
      <div
        v-if="isPending"
        class="bg-base-white p-5 rounded-lg border border-gray-warm-300 flex flex-col gap-3"
      >
        <Skeleton class="h-6 w-48" />
        <Skeleton class="h-9 w-full" />
        <Skeleton class="h-9 w-3/4" />
      </div>

      <!-- Error state -->
      <Alert v-else-if="isError" variant="destructive">
        <Icon name="alert-circle" stroke-color="error-700" />
        <AlertTitle>{{ t('components.deployment-bastion-modal.error-loading') }}</AlertTitle>
      </Alert>

      <form v-else class="flex flex-col gap-4" @submit.prevent.stop="form.handleSubmit">
        <Alert v-if="errorMessage" variant="destructive">
          <Icon name="alert-circle" stroke-color="error-700" />
          <AlertTitle>{{ errorMessage }}</AlertTitle>
        </Alert>

        <form.Subscribe>
          <!-- SSH section -->
          <section
            class="bg-base-white p-5 rounded-lg border border-gray-warm-300 flex flex-col gap-4"
          >
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <Icon name="terminal-square" size="md" stroke-color="gray-warm-700" />
                <h3 class="font-semibold text-gray-warm-700">
                  {{ t('components.domain.access.bastion.ssh.label') }}
                </h3>
              </div>
              <form.Field v-slot="{ field }" name="sshEnabled">
                <Switch
                  :id="field.name"
                  :name="field.name"
                  :model-value="field.state.value"
                  @update:model-value="field.handleChange"
                />
              </form.Field>
            </div>
            <div v-if="form.getFieldValue('sshEnabled')" class="grid grid-cols-2 gap-4">
              <form.Field v-slot="{ field }" name="sshPort">
                <div>
                  <FieldLabel class="mb-2">
                    {{ t('components.domain.access.bastion.ssh.port.label') }}
                  </FieldLabel>
                  <FieldContent>
                    <InputField
                      :id="field.name"
                      :name="field.name"
                      :model-value="field.state.value"
                      type="number"
                      min="1"
                      max="65535"
                      @blur="field.handleBlur"
                      @update:model-value="(value) => field.handleChange(Number(value))"
                    />
                  </FieldContent>
                  <FieldError :errors="field.state.meta.errors" />
                </div>
              </form.Field>
            </div>
          </section>

          <!-- HTTP / HTTPS section -->
          <section
            class="bg-base-white p-5 rounded-lg border border-gray-warm-300 flex flex-col gap-4"
          >
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <Icon name="globe-04" size="md" stroke-color="gray-warm-700" />
                <h3 class="font-semibold text-gray-warm-700">
                  {{ t('components.domain.access.bastion.http-https.label') }}
                </h3>
              </div>
              <form.Field v-slot="{ field }" name="httpEnabled">
                <Switch
                  :id="field.name"
                  :name="field.name"
                  :model-value="field.state.value"
                  @update:model-value="field.handleChange"
                />
              </form.Field>
            </div>
            <div v-if="form.getFieldValue('httpEnabled')" class="grid grid-cols-2 gap-4">
              <form.Field v-slot="{ field }" name="httpPort">
                <div>
                  <FieldLabel class="mb-2">
                    {{ t('components.domain.access.bastion.http-https.http-port.label') }}
                  </FieldLabel>
                  <FieldContent>
                    <InputField
                      :id="field.name"
                      :name="field.name"
                      :model-value="field.state.value"
                      type="number"
                      min="1"
                      max="65535"
                      @blur="field.handleBlur"
                      @update:model-value="(value) => field.handleChange(Number(value))"
                    />
                  </FieldContent>
                  <FieldError :errors="field.state.meta.errors" />
                </div>
              </form.Field>
              <form.Field v-slot="{ field }" name="httpsPort">
                <div>
                  <FieldLabel class="mb-2">
                    {{ t('components.domain.access.bastion.http-https.https-port.label') }}
                  </FieldLabel>
                  <FieldContent>
                    <InputField
                      :id="field.name"
                      :name="field.name"
                      :model-value="field.state.value"
                      type="number"
                      min="1"
                      max="65535"
                      @blur="field.handleBlur"
                      @update:model-value="(value) => field.handleChange(Number(value))"
                    />
                  </FieldContent>
                  <FieldError :errors="field.state.meta.errors" />
                </div>
              </form.Field>
            </div>
          </section>
        </form.Subscribe>
      </form>
    </div>

    <template #footer>
      <div class="flex justify-between w-full px-6">
        <Button size="lg" hierarchy="link-color" :disabled="isSaving" @click="emit('close')">
          {{ t('modals.cancel') }}
        </Button>
        <Button
          size="lg"
          hierarchy="primary"
          :disabled="isPending || isError || isSaving"
          @click="form.handleSubmit"
        >
          {{
            isSaving ? t('common.loading') : t('components.deployment-bastion-modal.buttons.save')
          }}
        </Button>
      </div>
    </template>
  </Modal>
</template>
