<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter, RouterLink, onBeforeRouteLeave } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuery, useMutation } from '@tanstack/vue-query'

import {
  getMediaOptions,
  listMediaInstallsOptions,
  createDesktopFromMediaMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { CreateDesktopFromMedia } from '@/gen/oas/apiv4'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { InputField } from '@/components/input-field'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'

import DomainAccessForm from '@/components/domain/DomainAccessForm.vue'
import DomainHardwareForm from '@/components/domain/DomainHardwareForm.vue'
import { useDomainInfoForm } from '@/composables/useDomainInfoForm'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const mediaId = computed(() => route.params.mediaId as string)

const {
  data: mediaInfo,
  isPending: mediaLoading,
  isError: mediaError
} = useQuery(
  getMediaOptions({
    path: { media_id: mediaId.value }
  })
)

if (mediaError.value) {
  router.push({ name: 'media' })
}

const { data: osTemplates, isPending: osTemplatesLoading } = useQuery(listMediaInstallsOptions())

const selectedOsTemplateId = ref<string>('')

const infoForm = useDomainInfoForm({})

const accessFormRef = ref<{
  getFormData: () => Record<string, unknown>
  isValid: boolean
} | null>(null)
const hardwareFormRef = ref<{
  getFormData: () => Record<string, unknown>
  isValid: boolean
  getInterfaces: () => string[]
  addInterface: (ifaceId: string) => void
  removeInterface: (ifaceId: string) => void
  interfaces: { value: string[] }
} | null>(null)

const hardwareInterfaces = computed<string[]>(() => hardwareFormRef.value?.interfaces?.value ?? [])

function handleAddInterfaceFromAccessForm(ifaceId: string) {
  hardwareFormRef.value?.addInterface(ifaceId)
}

const infoIsValid = infoForm.useStore((state) => state.isValid)
const infoIsDirty = infoForm.useStore((state) => !state.isPristine)
const formsValid = computed(() => {
  return (
    infoIsValid.value &&
    !!selectedOsTemplateId.value &&
    (accessFormRef.value?.isValid ?? true) &&
    (hardwareFormRef.value?.isValid ?? true)
  )
})

const isDirty = ref(false)
infoForm.store.subscribe(() => {
  if (infoIsDirty.value) isDirty.value = true
})

const createErrorCode = ref<string | undefined>(undefined)

const {
  mutate: submitCreate,
  isPending: createIsPending,
  isError: createIsError
} = useMutation({
  ...createDesktopFromMediaMutation(),
  onSuccess: (data) => {
    isDirty.value = false
    router.push({
      name: 'single-desktop',
      params: { desktopId: data.id, action: 'desktop-created' }
    })
  },
  onError: (error) => {
    createErrorCode.value = 'description_code' in error ? String(error.description_code) : 'generic'
  }
})

function isInvalid(field: { state: { meta: { isTouched: boolean; isValid: boolean } } }) {
  return field.state.meta.isTouched && !field.state.meta.isValid
}

interface HardwareFormData {
  vcpus: number
  memory: number
  diskBus: string
  diskSize: number
  videos: string
  bootOrder: string
  interfaces: string[]
  isos: string[]
  floppies: string[]
  reservables: { vgpus: string[] | null }
}

interface AccessFormData {
  credentials: { username: string; password: string }
  fullscreen: boolean
  viewers: Record<string, { options: Record<string, unknown> | null }>
}

function handleSubmit() {
  createErrorCode.value = undefined
  if (!formsValid.value || !mediaInfo.value) return

  const access = accessFormRef.value?.getFormData() as AccessFormData | undefined
  const hw = hardwareFormRef.value?.getFormData() as HardwareFormData | undefined
  if (!access || !hw) return

  const body: CreateDesktopFromMedia = {
    media_id: mediaId.value,
    kind: mediaInfo.value.kind,
    os_template: selectedOsTemplateId.value,
    name: infoForm.getFieldValue('name'),
    description: infoForm.getFieldValue('description'),
    guest_properties: {
      credentials: access.credentials,
      fullscreen: access.fullscreen,
      viewers: access.viewers
    },
    hardware: {
      vcpus: hw.vcpus,
      memory: hw.memory,
      disk_bus: hw.diskBus,
      disk_size: hw.diskSize,
      videos: [hw.videos],
      boot_order: [hw.bootOrder],
      interfaces: hw.interfaces,
      reservables: hw.reservables as CreateDesktopFromMedia['hardware']['reservables']
    }
  }

  submitCreate({ body })
}

// Unsaved-changes guard
const showUnsavedGuard = ref(false)
const pendingNavigation = ref<(() => void) | null>(null)

onBeforeRouteLeave((to, from, next) => {
  if (!isDirty.value || createIsPending.value) {
    next()
    return
  }
  pendingNavigation.value = () => next()
  showUnsavedGuard.value = true
  next(false)
})

function confirmLeave() {
  isDirty.value = false
  showUnsavedGuard.value = false
  pendingNavigation.value?.()
  pendingNavigation.value = null
}

function cancelLeave() {
  showUnsavedGuard.value = false
  pendingNavigation.value = null
}
</script>

<template>
  <div
    class="flex flex-col-reverse md:flex-row items-start justify-between max-w-480 w-full mx-auto mb-8 gap-4"
  >
    <div class="flex flex-col gap-1">
      <h1 class="text-lg font-bold text-gray-warm-900">
        {{ t('views.new-from-media.title') }}
      </h1>
      <h2 class="text-sm font-regular text-gray-warm-700">
        {{ t('views.new-from-media.subtitle', { media: mediaInfo?.name ?? '' }) }}
      </h2>
    </div>

    <div class="flex gap-4 md:w-auto w-full justify-end">
      <Button :as="RouterLink" :to="{ name: 'media' }" hierarchy="link-color">
        {{ t('views.new-from-media.header.cancel') }}
      </Button>
      <Button
        type="submit"
        :disabled="!formsValid || createIsPending"
        :icon="createIsPending ? 'loading-02' : ''"
        icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
        @click="handleSubmit"
      >
        {{ t('views.new-from-media.header.create') }}
      </Button>
    </div>
  </div>

  <main class="max-w-320 w-full mx-auto flex flex-col gap-[24px]">
    <Alert v-if="createIsError" variant="destructive">
      <FeaturedIconOutline kind="outline" color="error" />
      <AlertTitle>{{ t('views.new-from-media.errors.title') }}</AlertTitle>
      <AlertDescription>{{
        t(`api.new-from-media.errors.${createErrorCode}`, t('api.new-from-media.errors.generic'))
      }}</AlertDescription>
    </Alert>

    <template v-if="mediaLoading">
      <Skeleton class="h-48 w-full rounded-2xl" />
    </template>

    <template v-else>
      <section class="flex flex-col gap-4">
        <div class="flex flex-col gap-0.5">
          <h3 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-from-media.info.title') }}
          </h3>
          <p class="text-sm font-regular text-gray-warm-700">
            {{ t('views.new-from-media.info.description') }}
          </p>
        </div>

        <form class="flex flex-col gap-4" @submit.prevent="handleSubmit">
          <infoForm.Field v-slot="{ field }" name="name">
            <Field :data-invalid="isInvalid(field)">
              <FieldLabel :for="field.name">
                {{ t('components.domain.info.name.label') }}
              </FieldLabel>
              <InputField
                :id="field.name"
                :name="field.name"
                :model-value="field.state.value"
                :placeholder="t('components.domain.info.name.placeholder')"
                :aria-invalid="isInvalid(field)"
                :destructive="isInvalid(field)"
                maxlength="50"
                autocomplete="off"
                type="text"
                @blur="field.handleBlur"
                @input="field.handleChange(($event.target as HTMLInputElement).value)"
              />
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
            </Field>
          </infoForm.Field>

          <infoForm.Field v-slot="{ field }" name="description">
            <Field :data-invalid="isInvalid(field)">
              <FieldLabel :for="field.name">
                {{ t('components.domain.info.description.label') }}
              </FieldLabel>
              <Textarea
                :id="field.name"
                :name="field.name"
                :model-value="field.state.value"
                :placeholder="t('components.domain.info.description.placeholder')"
                maxlength="255"
                class="bg-base-white resize-none"
                @update:model-value="(v) => field.handleChange(String(v))"
              />
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
            </Field>
          </infoForm.Field>
        </form>
      </section>

      <section class="flex flex-col gap-4">
        <div class="flex flex-col gap-0.5">
          <h3 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-from-media.os-template.title') }}
          </h3>
          <p class="text-sm font-regular text-gray-warm-700">
            {{ t('views.new-from-media.os-template.description') }}
          </p>
        </div>
        <Skeleton v-if="osTemplatesLoading" class="h-10 w-full rounded-md" />
        <Field v-else>
          <FieldLabel for="os-template-select">
            {{ t('views.new-from-media.os-template.label') }}
          </FieldLabel>
          <Select v-model="selectedOsTemplateId" name="os-template-select">
            <SelectTrigger class="min-w-[200px]">
              <SelectValue :placeholder="t('views.new-from-media.os-template.placeholder')" />
            </SelectTrigger>
            <SelectContent position="item-aligned">
              <SelectItem v-for="tpl in osTemplates ?? []" :key="tpl.id" :value="tpl.id">
                {{ tpl.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </Field>
      </section>

      <section class="flex flex-col gap-4">
        <div class="flex flex-col gap-0.5">
          <h3 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-from-media.access.title') }}
          </h3>
          <p class="text-sm font-regular text-gray-warm-700">
            {{ t('views.new-from-media.access.description') }}
          </p>
        </div>
        <DomainAccessForm
          ref="accessFormRef"
          :show-bastion-config="false"
          :hardware-interfaces="hardwareInterfaces"
          :on-request-add-interface="handleAddInterfaceFromAccessForm"
        />
      </section>

      <section class="flex flex-col gap-4">
        <div class="flex flex-col gap-0.5">
          <h3 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.new-from-media.hardware.title') }}
          </h3>
          <p class="text-sm font-regular text-gray-warm-700">
            {{ t('views.new-from-media.hardware.description') }}
          </p>
        </div>
        <DomainHardwareForm ref="hardwareFormRef" :show-disk-size="true" />
      </section>
    </template>
  </main>

  <AlertModal
    :open="showUnsavedGuard"
    level="warning"
    size="md"
    :title="t('views.new-from-media.unsaved-changes.title')"
    :description="t('views.new-from-media.unsaved-changes.description')"
    @update:open="showUnsavedGuard = $event"
    @cancel="cancelLeave"
  >
    <template #footer>
      <Button hierarchy="link-gray" @click="cancelLeave">
        {{ t('views.new-from-media.unsaved-changes.stay') }}
      </Button>
      <Button hierarchy="destructive" @click="confirmLeave">
        {{ t('views.new-from-media.unsaved-changes.leave') }}
      </Button>
    </template>
  </AlertModal>
</template>
