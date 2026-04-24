<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

import { isInvalid } from '@/lib/utils'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { InputField } from '@/components/input-field'
import { Button } from '@/components/ui/button'
import { FeaturedIconOutline } from '@/components/icon/featured-outline'
import { Textarea } from '@/components/ui/textarea'

import { DesktopCardBase, DesktopCardHeader } from '@/components/desktop-card'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

const { t, d } = useI18n()

interface Props {
  form: any // TODO: type this
  index: number
  open?: boolean
  autoFocus?: boolean
}

const props = withDefaults(defineProps<Props>(), {})

const emit = defineEmits<{
  changeTemplate: []
  deleteDesktop: []
  updateHardware: [restrictedFieldsDetails?: any]
}>()

const open = ref<boolean>(props.open || false)

const nameInputRef = ref<InstanceType<typeof InputField> | null>(null)

onMounted(() => {
  if (props.autoFocus) {
    nextTick(() => {
      const input = nameInputRef.value?.$el?.querySelector('input') as HTMLInputElement | null
      input?.focus()
      input?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }
})

// Format value for display (helper function)
const formatValue = (value: any) => {
  if (Array.isArray(value)) {
    return value.map((v) => v.name || v.id || v).join(', ') || 'None'
  }
  return value?.name || value?.id || value || 'None'
}

// Get list of restricted fields with their restrictions for display
const restrictedFieldsDetails = computed(() => {
  const limitedFields = props.form.useStore(
    (state: any) => state.values.desktops?.[props.index]?.limited_hardware
  ).value
  if (!limitedFields || typeof limitedFields !== 'object') return []

  const fieldNameMap: Record<string, string> = {
    vcpus: t('components.domain.hardware.vcpus.label'),
    memory: t('components.domain.hardware.memory.label'),
    disk_bus: t('components.domain.hardware.disk-bus.label'),
    videos: t('components.domain.hardware.videos.label'),
    boot_order: t('components.domain.hardware.boot-order.label'),
    isos: t('components.domain.hardware.isos.label'),
    floppies: t('components.domain.hardware.floppies.label'),
    vgpus: t('components.domain.hardware.vgpus.label'),
    interfaces: t('components.domain.hardware.networks.label')
  }

  return Object.entries(limitedFields).map(([key, value]: [string, any]) => ({
    name: fieldNameMap[key] || key,
    oldValue: formatValue(value.old_value),
    newValue: formatValue(value.new_value)
  }))
})

const formPrefix = computed(() => `desktops[${props.index}]`)
</script>

<template>
  <Collapsible v-model:open="open">
    <div class="flex items-center gap-4">
      <CollapsibleTrigger class="flex items-center gap-4 mr-auto overflow-hidden">
        <Button
          hierarchy="secondary-gray"
          class="p-[10px]"
          :icon="open ? 'chevron-up' : 'chevron-down'"
        />
        <props.form.Subscribe v-slot="{ values }">
          <span
            class="text-lg font-semibold text-gray-warm-900 text-start text-ellipsis overflow-hidden whitespace-nowrap"
            >{{
              t(
                `components.deployments.form-desktop-card.header.title${values.desktops[props.index]?.name ? '-name' : ''}`,
                {
                  index: props.index + 1,
                  'desktop-name': values.desktops[props.index]?.name
                }
              )
            }}
          </span>
        </props.form.Subscribe>
      </CollapsibleTrigger>

      <Button hierarchy="secondary-gray" @click="emit('changeTemplate')">{{
        t('components.deployments.form-desktop-card.header.buttons.change-template')
      }}</Button>
      <Button hierarchy="destructive" @click="emit('deleteDesktop')">{{
        t('components.deployments.form-desktop-card.header.buttons.delete-desktop')
      }}</Button>
    </div>
    <CollapsibleContent class="flex gap-8 mt-4">
      <div class="flex flex-col gap-[24px] items-center shrink-0">
        <div class="flex flex-col gap-[16px]">
          <div class="flex flex-col gap-0.5">
            <h1 class="text-lg font-semibold text-gray-warm-900">
              {{ t('components.deployments.form-desktop-card.sections.preview.title') }}
            </h1>
            <h2 class="text-sm font-regular text-gray-warm-700">
              {{ t('components.deployments.form-desktop-card.sections.preview.subtitle') }}
            </h2>
          </div>

          <div class="flex flex-row gap-4">
            <props.form.Subscribe v-slot="{ values }">
              <DesktopCardBase
                desktop-kind="deployment"
                :image-url="values.desktops[props.index].image?.url || ''"
                :show-network-overlay="false"
              >
                <template #header-actions>
                  <Button icon="image-plus" hierarchy="secondary-gray" size="sm" />
                </template>
                <template #header>
                  <!-- <InputField placeholder="Desktop Name" />
                  <Textarea class="bg-base-white resize-none" placeholder="Desktop Description" /> -->

                  <DesktopCardHeader
                    :name="values.desktops[props.index].name"
                    :description="values.desktops[props.index].description"
                  />
                </template>
                <template #footer>
                  <Button
                    icon="play"
                    icon-class="fill-current"
                    hierarchy="secondary-color"
                    size="sm"
                    class="shrink-0"
                    disabled
                  >
                    {{ t('components.desktops.desktop-card.status.stopped.action') }}
                  </Button>
                </template>
              </DesktopCardBase>
            </props.form.Subscribe>

            <form class="flex flex-col gap-4 w-96" @submit.prevent="props.form.handleSubmit">
              <props.form.Field
                v-slot="{ field }"
                :key="`${formPrefix}.name`"
                :name="`${formPrefix}.name`"
              >
                <Field>
                  <FieldLabel :for="field.name">{{
                    t('components.deployments.form-desktop-card.sections.preview.fields.name.label')
                  }}</FieldLabel>
                  <InputField
                    :id="field.name"
                    ref="nameInputRef"
                    :name="field.name"
                    :model-value="field.state.value"
                    :placeholder="
                      t(
                        'components.deployments.form-desktop-card.sections.preview.fields.name.placeholder'
                      )
                    "
                    autocomplete="off"
                    type="text"
                    @blur="field.handleBlur"
                    @input="field.handleChange($event.target.value)"
                    maxlength="50"
                  />
                </Field>
              </props.form.Field>

              <props.form.Field
                v-slot="{ field }"
                :key="`${formPrefix}.description`"
                :name="`${formPrefix}.description`"
              >
                <Field>
                  <FieldLabel :for="field.name">{{
                    t(
                      'components.deployments.form-desktop-card.sections.preview.fields.description.label'
                    )
                  }}</FieldLabel>
                  <Textarea
                    :id="field.name"
                    :name="field.name"
                    :model-value="field.state.value"
                    class="w-full bg-base-white h-32 resize-none"
                    :placeholder="
                      t(
                        'components.deployments.form-desktop-card.sections.preview.fields.description.placeholder'
                      )
                    "
                    autocomplete="off"
                    @blur="field.handleBlur"
                    @input="field.handleChange($event.target.value)"
                    maxlength="255"
                  />
                </Field>
              </props.form.Field>
            </form>
          </div>
        </div>
      </div>

      <div class="flex flex-col gap-[24px] items-center">
        <div class="flex flex-col gap-[16px] w-full">
          <div class="flex flex-col gap-0.5">
            <h1 class="text-lg font-semibold text-gray-warm-900">
              {{ t('components.deployments.form-desktop-card.sections.hardware.title') }}
            </h1>
            <h2 class="text-sm font-regular text-gray-warm-700">
              {{ t('components.deployments.form-desktop-card.sections.hardware.subtitle') }}
            </h2>
          </div>

          <div class="flex flex-col gap-4 items-start">
            <Button
              hierarchy="secondary-gray"
              icon="settings-02"
              @click="emit('updateHardware', restrictedFieldsDetails)"
              >{{ t('components.deployments.form-desktop-card.sections.hardware.button') }}</Button
            >

            <!-- Informational alert for limited hardware fields -->
            <Alert
              v-if="restrictedFieldsDetails.length > 0"
              variant="default"
              class="w-full border-error-600"
            >
              <FeaturedIconOutline kind="outline" color="gray" />
              <AlertTitle>{{ t('views.new-desktop.step-2.hardware-limited.title') }}</AlertTitle>
              <AlertDescription>
                {{ t('views.new-desktop.step-2.hardware-limited.description') }}
                <ul v-if="restrictedFieldsDetails.length" class="mt-3 space-y-2">
                  <li v-for="field in restrictedFieldsDetails" :key="field.name" class="text-sm">
                    <span class="font-semibold text-error-600">{{ field.name }}: </span>
                    <span class="text-error-600">{{ field.oldValue }} → {{ field.newValue }}</span>
                  </li>
                </ul>
              </AlertDescription>
            </Alert>
          </div>
        </div>
      </div>
    </CollapsibleContent>
  </Collapsible>
</template>
