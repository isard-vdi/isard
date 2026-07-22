<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { isInvalid } from '@/lib/utils'

import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldLabel
} from '@/components/ui/field'
import { InputField } from '@/components/input-field'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import Switch from '@/components/ui/switch/Switch.vue'
import { Icon } from '@/components/icon'
import { Textarea } from '@/components/ui/textarea'

import { DesktopCardBaseStacked, DesktopCardHeader } from '@/components/desktop-card'
import { BadgeInfo } from '@/components/badge/info'
import ChangeImageModal from '@/components/domain/ChangeImageModal.vue'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const { t, d } = useI18n()

interface Props {
  form: any // TODO: type this
  showCreateOwnerDesktop: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showCreateOwnerDesktop: true
})

const emit = defineEmits<{
  submit: []
}>()

const formImage = props.form.useStore((state: any) => state.values.image)

const showChangeImageModal = ref(false)

function handleImageSelected(image: { id: string; type: string; url?: string }) {
  props.form.setFieldValue('image', {
    id: image.id,
    type: image.type,
    url: image.url ?? ''
  })
}
</script>

<template>
  <ChangeImageModal
    :open="showChangeImageModal"
    :current-image="formImage"
    @select="handleImageSelected"
    @close="showChangeImageModal = false"
  />

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-8">
    <div class="flex flex-col gap-[16px]">
      <div class="flex flex-col gap-0.5 lg:max-w-117.5">
        <h1 class="text-lg font-semibold text-gray-warm-900">
          {{ t('components.deployments.form-sections.preview.title') }}
        </h1>
        <h2 class="text-sm font-regular text-gray-warm-700">
          {{ t('components.deployments.form-sections.preview.subtitle') }}
        </h2>
      </div>

      <div class="flex justify-center lg:justify-start">
        <props.form.Subscribe v-slot="{ values }">
          <DesktopCardBaseStacked
            desktop-kind="deployment"
            :image-url="values.image?.url || ''"
            :show-network-overlay="false"
          >
            <template #header-actions>
              <Button
                icon="image-plus"
                hierarchy="secondary-gray"
                size="sm"
                @click="showChangeImageModal = true"
              />
            </template>
            <template #header>
              <DesktopCardHeader :name="values.name" :description="values.description" />
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
          </DesktopCardBaseStacked>
        </props.form.Subscribe>
      </div>
    </div>

    <div class="flex flex-col gap-[16px]">
      <div class="flex flex-col gap-0.5">
        <h1 class="text-lg font-semibold text-gray-warm-900">
          {{ t('components.deployments.form-sections.info.title') }}
        </h1>
        <h2 class="text-sm font-regular text-gray-warm-700">
          {{ t('components.deployments.form-sections.info.subtitle') }}
        </h2>
      </div>

      <form class="contents" @submit.prevent="emit('submit')">
        <props.form.Field v-slot="{ field }" name="name">
          <Field>
            <FieldLabel :for="field.name">{{
              t('components.deployments.form-sections.info.fields.name.label')
            }}</FieldLabel>
            <InputField
              :id="field.name"
              :name="field.name"
              :model-value="field.state.value"
              :placeholder="t('components.deployments.form-sections.info.fields.name.placeholder')"
              autofocus
              autocomplete="off"
              type="text"
              maxlength="50"
              @blur="field.handleBlur"
              @input="field.handleChange($event.target.value)"
            />
          </Field>
        </props.form.Field>

        <props.form.Field v-slot="{ field }" name="description">
          <Field>
            <FieldLabel :for="field.name">{{
              t('components.deployments.form-sections.info.fields.description.label')
            }}</FieldLabel>

            <Textarea
              :id="field.name"
              :name="field.name"
              :model-value="field.state.value"
              class="w-full bg-base-white h-32 resize-none"
              :placeholder="
                t('components.deployments.form-sections.info.fields.description.placeholder')
              "
              autocomplete="off"
              maxlength="255"
              @blur="field.handleBlur"
              @input="field.handleChange($event.target.value)"
            />
          </Field>
        </props.form.Field>
      </form>
    </div>

    <div class="flex flex-col gap-[16px]">
      <div class="flex flex-col gap-0.5">
        <h1 class="text-lg font-semibold text-gray-warm-900">
          {{ t('components.deployments.form-sections.visibility.title') }}
        </h1>
        <h2 class="text-sm font-regular text-gray-warm-700">
          {{ t('components.deployments.form-sections.visibility.subtitle') }}
        </h2>
      </div>

      <form @submit.prevent="emit('submit')">
        <props.form.Field v-slot="{ field }" name="visible" class="contents">
          <Field orientation="horizontal" :data-invalid="isInvalid(field)">
            <Switch
              :id="field.name"
              :name="field.name"
              :model-value="field.state.value"
              :aria-invalid="isInvalid(field)"
              @update:model-value="field.handleChange"
            />
            <FieldContent>
              <FieldLabel :for="field.name">{{
                t('components.deployments.form-sections.visibility.fields.visible.label')
              }}</FieldLabel>
              <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
            </FieldContent>
          </Field>
        </props.form.Field>
      </form>
    </div>
    <div class="flex flex-col gap-[16px]">
      <props.form.Subscribe v-slot="{ values }">
        <div class="flex flex-col gap-0.5">
          <div class="flex flex-row gap-4">
            <h1 class="text-lg font-semibold text-gray-warm-900">
              {{ t('components.deployments.form-sections.alloweds.title') }}
            </h1>
            <BadgeInfo
              icon="users-01"
              :content="(values.alloweds?.groups?.length || 0).toString()"
              class="text-sm px-2"
            />
            <BadgeInfo
              icon="user-01"
              :content="(values.alloweds?.users?.length || 0).toString()"
              class="text-sm px-2"
            />
          </div>
          <i18n-t
            keypath="components.deployments.form-sections.alloweds.subtitle"
            tag="h2"
            class="text-sm font-regular text-gray-warm-700"
          >
            <template #groups>
              <b>{{ t('users.count.groups', values.alloweds?.groups?.length || 0) }}</b>
            </template>
            <template #users>
              <b>{{ t('users.count.users', values.alloweds?.users?.length || 0) }}</b>
            </template>
          </i18n-t>
        </div>
      </props.form.Subscribe>

      <div>
        <Button icon="plus" hierarchy="secondary-gray">{{
          t('components.deployments.form-sections.alloweds.fields.alloweds.button')
        }}</Button>
      </div>
    </div>

    <div class="flex flex-col gap-[16px] col-span-full">
      <div class="flex flex-col gap-0.5">
        <h1 class="text-lg font-semibold text-gray-warm-900">
          {{ t('components.deployments.form-sections.user-permissions.title') }}
        </h1>
        <h2 class="text-sm font-regular text-gray-warm-700">
          {{ t('components.deployments.form-sections.user-permissions.subtitle') }}
        </h2>
      </div>

      <props.form.Field v-slot="{ field }" name="permissions.recreate" class="contents">
        <Field orientation="horizontal" :data-invalid="isInvalid(field)">
          <Switch
            :id="field.name"
            :name="field.name"
            :model-value="field.state.value"
            :aria-invalid="isInvalid(field)"
            @update:model-value="field.handleChange"
          />
          <FieldContent>
            <FieldLabel :for="field.name">
              <BadgeInfo icon="refresh-cw-01" class="px-2 rounded-md" />

              {{ t('components.deployments.form-sections.user-permissions.fields.recreate.label') }}

              <Tooltip>
                <TooltipTrigger as-child>
                  <span class="pointer-cursor pointer-coarse:hidden"
                    ><Icon name="help-circle" size="sm"
                  /></span>
                </TooltipTrigger>
                <TooltipContent
                  :title="
                    t(
                      'components.deployments.form-sections.user-permissions.fields.recreate.description'
                    )
                  "
                />
              </Tooltip>
            </FieldLabel>
            <FieldDescription class="pointer-fine:hidden">{{
              t('components.deployments.form-sections.user-permissions.fields.recreate.description')
            }}</FieldDescription>
            <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
          </FieldContent>
        </Field>
      </props.form.Field>
    </div>

    <div v-if="props.showCreateOwnerDesktop" class="flex flex-col gap-[16px]">
      <div class="flex flex-col gap-0.5">
        <h1 class="text-lg font-semibold text-gray-warm-900">
          {{ t('components.deployments.form-sections.other-options.title') }}
        </h1>
      </div>

      <props.form.Field v-slot="{ field }" name="createOwnerDesktop" class="contents">
        <Field orientation="horizontal" :data-invalid="isInvalid(field)">
          <Switch
            :id="field.name"
            :name="field.name"
            :model-value="field.state.value"
            :aria-invalid="isInvalid(field)"
            @update:model-value="field.handleChange"
          />
          <FieldContent>
            <FieldLabel :for="field.name"
              >{{
                t(
                  'components.deployments.form-sections.other-options.fields.create-owner-desktop.label'
                )
              }}
              <Tooltip>
                <TooltipTrigger as-child>
                  <span class="pointer-cursor pointer-coarse:hidden"
                    ><Icon name="help-circle" size="sm"
                  /></span>
                </TooltipTrigger>
                <TooltipContent
                  :title="
                    t(
                      'components.deployments.form-sections.other-options.fields.create-owner-desktop.description'
                    )
                  "
                />
              </Tooltip>
            </FieldLabel>
            <FieldDescription class="pointer-fine:hidden">{{
              t(
                'components.deployments.form-sections.other-options.fields.create-owner-desktop.description'
              )
            }}</FieldDescription>
            <FieldError v-if="isInvalid(field)" :errors="field.state.meta.errors" />
          </FieldContent>
        </Field>
      </props.form.Field>
    </div>
  </div>
</template>
