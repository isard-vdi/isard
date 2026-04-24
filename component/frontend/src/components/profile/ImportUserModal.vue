<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMutation } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import Modal from '@/components/modal/Modal.vue'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/input-field'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Icon } from '@/components/icon'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { useI18n } from 'vue-i18n'
import { migrationImportUserApiV4ItemUserMigrationImportUserPutMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

interface Props {
  open?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { t } = useI18n()
const router = useRouter()

const importToken = ref('')
const apiError = ref('')

watch(
  () => props.open,
  (newVal) => {
    if (newVal) {
      importToken.value = ''
      apiError.value = ''
    }
  }
)

const handleClose = () => {
  if (isSubmitting.value) return
  emit('update:open', false)
}

const { mutateAsync: importUser, isPending: isSubmitting } = useMutation(
  migrationImportUserApiV4ItemUserMigrationImportUserPutMutation()
)

const handleSubmit = async () => {
  if (!importToken.value.trim() || isSubmitting.value) return
  apiError.value = ''

  try {
    await importUser({ body: { token: importToken.value.trim() } })
    emit('update:open', false)
    router.push({ name: 'migration' })
  } catch (error: unknown) {
    const descriptionCode =
      error && typeof error === 'object' && 'response' in error
        ? (error as { response?: { data?: { description_code?: string } } }).response?.data
            ?.description_code
        : undefined
    if (descriptionCode) {
      apiError.value = t(`components.profile.import-user-modal.errors.${descriptionCode}`)
    } else {
      apiError.value =
        t('components.profile.import-user-modal.errors.generic') || 'An error occurred'
    }
  }
}
</script>

<template>
  <Modal
    :open="props.open"
    :title="t('components.profile.import-user-modal.title')"
    size="2xl"
    :close-on-backdrop-click="!isSubmitting"
    @close="handleClose"
  >
    <div class="flex flex-col gap-6 pb-2">
      <div>
        <p class="text-base font-semibold text-gray-warm-900 mb-2">
          {{ t('components.profile.import-user-modal.description') }}
        </p>
      </div>

      <!-- Instructions Card -->
      <div class="bg-gray-warm-50 border border-gray-warm-200 rounded-lg p-5">
        <div class="flex items-start gap-3">
          <div class="flex-shrink-0 mt-0.5">
            <FeaturedIconOutline name="info-circle" kind="outline" color="brand" size="md" />
          </div>
          <div class="flex-1">
            <h4 class="text-sm font-semibold text-gray-warm-900 mb-3">
              {{ t('components.profile.import-user-modal.instructions-title') }}
            </h4>
            <div class="space-y-2 text-sm text-gray-warm-700 list-disc list-inside">
              <li>
                {{ t('components.profile.import-user-modal.migration-instructions1') }}
              </li>
              <li>
                {{ t('components.profile.import-user-modal.migration-instructions2') }}
              </li>
              <li>
                {{ t('components.profile.import-user-modal.migration-instructions3') }}
              </li>
            </div>
          </div>
        </div>
      </div>

      <div class="space-y-3">
        <Label class="block text-sm font-medium text-gray-warm-900">
          {{ t('components.profile.import-user-modal.token-label') }}
        </Label>
        <InputField
          v-model="importToken"
          :placeholder="t('components.profile.import-user-modal.placeholder')"
          icon="key-01"
          :disabled="isSubmitting"
        />
      </div>

      <!-- Error -->
      <Alert v-if="apiError" variant="destructive">
        <div class="flex items-start gap-3">
          <Icon name="alert-circle" size="md" stroke-color="currentColor" />
          <div>
            <AlertTitle>{{ t('components.profile.import-user-modal.errors.title') }}</AlertTitle>
            <AlertDescription>{{ apiError }}</AlertDescription>
          </div>
        </div>
      </Alert>
    </div>

    <template #footer>
      <div class="w-full flex justify-end gap-3 px-6 mt-1">
        <Button hierarchy="secondary-gray" size="lg" :disabled="isSubmitting" @click="handleClose">
          {{ t('forms.common.cancel') }}
        </Button>
        <Button
          hierarchy="primary"
          size="lg"
          :disabled="!importToken || isSubmitting"
          @click="handleSubmit"
        >
          <Icon v-if="isSubmitting" name="loading-03" size="md" class="animate-spin" />
          {{ t('components.profile.import-user-modal.buttons.migrate') }}
        </Button>
      </div>
    </template>
  </Modal>
</template>
