<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  getDesktopImagesOptions,
  getDesktopImagesQueryKey,
  editDesktopMutation,
  getDesktopInfoQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { DomainImageOutput } from '@/gen/oas/apiv4/types.gen'

import { Modal } from '@/components/modal'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const ACCEPTED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif']
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024 // 5 MB

interface Props {
  open: boolean
  desktopId: string
  currentImage?: DomainImageOutput
}

const props = withDefaults(defineProps<Props>(), {
  currentImage: undefined
})

const emit = defineEmits<{
  close: []
  saved: []
}>()

const { t } = useI18n()
const queryClient = useQueryClient()

const {
  data: imagesResponse,
  isPending: imagesLoading,
  isError: imagesError
} = useQuery({
  ...getDesktopImagesOptions({
    query: { desktop_id: props.desktopId }
  }),
  enabled: computed(() => props.open && !!props.desktopId)
})

const images = computed<DomainImageOutput[]>(() => imagesResponse.value?.images ?? [])

const selectedImage = ref<DomainImageOutput | null>(null)

// Reset selection when modal opens
watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      selectedImage.value = props.currentImage ?? null
    }
  }
)

function isSelected(image: DomainImageOutput): boolean {
  if (!selectedImage.value) return false
  return selectedImage.value.id === image.id && selectedImage.value.type === image.type
}

function selectImage(image: DomainImageOutput) {
  selectedImage.value = image
}

const saveErrorCode = ref<string | undefined>(undefined)

const { mutate: saveImage, isPending: saveIsPending } = useMutation({
  ...editDesktopMutation(),
  onSuccess: () => {
    queryClient.invalidateQueries({
      queryKey: getDesktopInfoQueryKey({
        path: { desktop_id: props.desktopId }
      })
    })
    queryClient.invalidateQueries({
      queryKey: getDesktopImagesQueryKey({
        query: { desktop_id: props.desktopId }
      })
    })
    emit('saved')
    emit('close')
  },
  onError: (error) => {
    saveErrorCode.value = 'description_code' in error ? String(error.description_code) : 'generic'
  }
})

function handleSave() {
  if (!selectedImage.value) return
  saveErrorCode.value = undefined
  saveImage({
    path: { desktop_id: props.desktopId },
    body: {
      image: {
        id: selectedImage.value.id,
        type: selectedImage.value.type
      }
    }
  })
}

// --- Upload logic ---

const fileInput = ref<HTMLInputElement | null>(null)
const uploadErrorCode = ref<string | undefined>(undefined)

const { mutate: uploadImage, isPending: uploadIsPending } = useMutation({
  ...editDesktopMutation(),
  onSuccess: () => {
    uploadErrorCode.value = undefined
    queryClient.invalidateQueries({
      queryKey: getDesktopImagesQueryKey({
        query: { desktop_id: props.desktopId }
      })
    })
    queryClient.invalidateQueries({
      queryKey: getDesktopInfoQueryKey({
        path: { desktop_id: props.desktopId }
      })
    })
    if (fileInput.value) fileInput.value.value = ''
  },
  onError: (error) => {
    uploadErrorCode.value = 'description_code' in error ? String(error.description_code) : 'generic'
  }
})

function triggerFilePicker() {
  fileInput.value?.click()
}

function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
    uploadErrorCode.value = 'invalid_type'
    input.value = ''
    return
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    uploadErrorCode.value = 'too_large'
    input.value = ''
    return
  }

  const reader = new FileReader()
  reader.onload = () => {
    const result = reader.result
    if (typeof result !== 'string') {
      uploadErrorCode.value = 'generic'
      return
    }
    // Strip the 'data:<mime>;base64,' prefix to match the backend expectation
    const base64 = result.replace(/^data:[^;]+;base64,/, '')
    uploadImage({
      path: { desktop_id: props.desktopId },
      body: {
        image: {
          id: '',
          type: 'user',
          file: { data: base64, filename: file.name }
        }
      }
    })
  }
  reader.onerror = () => {
    uploadErrorCode.value = 'generic'
  }
  reader.readAsDataURL(file)
}

const anyPending = computed(() => saveIsPending.value || uploadIsPending.value)
</script>

<template>
  <Modal
    :open="props.open"
    size="3xl"
    :title="t('components.change-image-modal.title')"
    :description="t('components.change-image-modal.description')"
    :close-on-backdrop-click="!anyPending"
    @close="emit('close')"
  >
    <div class="py-4">
      <Alert v-if="saveErrorCode" variant="destructive" class="mb-4">
        <FeaturedIconOutline kind="outline" color="error" />
        <AlertTitle>{{ t('components.change-image-modal.errors.title') }}</AlertTitle>
        <AlertDescription>{{
          t(
            `components.change-image-modal.errors.${saveErrorCode}`,
            t('components.change-image-modal.errors.generic')
          )
        }}</AlertDescription>
      </Alert>

      <Alert v-if="uploadErrorCode" variant="destructive" class="mb-4">
        <FeaturedIconOutline kind="outline" color="error" />
        <AlertTitle>{{ t('components.change-image-modal.upload-errors.title') }}</AlertTitle>
        <AlertDescription>{{
          t(
            `components.change-image-modal.upload-errors.${uploadErrorCode}`,
            t('components.change-image-modal.upload-errors.generic')
          )
        }}</AlertDescription>
      </Alert>

      <Alert v-if="imagesError" variant="destructive" class="mb-4">
        <FeaturedIconOutline kind="outline" color="error" />
        <AlertTitle>{{ t('components.change-image-modal.load-error') }}</AlertTitle>
      </Alert>

      <div class="flex items-center justify-between mb-4">
        <p class="text-sm text-gray-warm-600">
          {{ t('components.change-image-modal.hint') }}
        </p>
        <input
          ref="fileInput"
          type="file"
          accept="image/png,image/jpeg,image/gif"
          class="hidden"
          @change="handleFileSelected"
        />
        <Button
          hierarchy="secondary-gray"
          size="sm"
          icon="image-plus"
          :disabled="anyPending"
          @click="triggerFilePicker"
        >
          <template v-if="uploadIsPending">
            <Icon name="loading-02" class="motion-safe:animate-[spin_2s_linear_infinite]" />
            {{ t('components.change-image-modal.upload.uploading') }}
          </template>
          <template v-else>
            {{ t('components.change-image-modal.upload.label') }}
          </template>
        </Button>
      </div>

      <div v-if="imagesLoading" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        <Skeleton v-for="n in 8" :key="n" class="h-24 w-full rounded-lg" />
      </div>
      <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        <button
          v-for="image in images"
          :key="`${image.type}-${image.id}`"
          type="button"
          :class="
            cn(
              'relative h-24 w-full overflow-hidden rounded-lg border-2 bg-gray-warm-100 transition-colors cursor-pointer',
              'hover:border-brand-400',
              'focus:outline-none focus:ring-3 focus:ring-brand',
              isSelected(image) ? 'border-brand-600' : 'border-gray-warm-200'
            )
          "
          @click="selectImage(image)"
        >
          <img
            v-if="image.url"
            :src="image.url"
            :alt="image.id"
            class="w-full h-full object-cover"
            loading="lazy"
          />
          <div
            v-if="isSelected(image)"
            class="absolute top-1 right-1 bg-brand-600 text-base-white text-xs rounded-full px-2 py-0.5"
          >
            {{ t('components.change-image-modal.selected') }}
          </div>
        </button>
      </div>
    </div>
    <template #footer>
      <Button hierarchy="link-gray" :disabled="anyPending" @click="emit('close')">
        {{ t('components.change-image-modal.cancel') }}
      </Button>
      <Button
        hierarchy="primary"
        :disabled="!selectedImage || anyPending"
        :icon="saveIsPending ? 'loading-02' : ''"
        icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
        @click="handleSave"
      >
        {{ t('components.change-image-modal.save') }}
      </Button>
    </template>
  </Modal>
</template>
