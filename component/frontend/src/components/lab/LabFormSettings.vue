<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'

import Label from '@/components/ui/label/Label.vue'
import Input from '@/components/ui/input/Input.vue'
import Switch from '@/components/ui/switch/Switch.vue'
import Separator from '@/components/ui/separator/Separator.vue'
import Badge from '@/components/ui/badge/Badge.vue'
import CardPreview from '@/components/ui/card/CardPreview.vue'
import { MultiSelect, type MultiSelectTagItemType } from '@/components/multi-select'

import { getAllUsersOptions, getAllGroupsOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

interface Props {
  name: string
  description: string
  visibility: boolean
  image: string
  selectedUsers: MultiSelectTagItemType[]
  selectedGroups: MultiSelectTagItemType[]
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false
})

const emit = defineEmits([
  'update:name',
  'update:description',
  'update:visibility',
  'update:image',
  'update:selectedUsers',
  'update:selectedGroups'
])

const { t } = useI18n()

const { isPending: getAllUsersIsPending, data: users } = useQuery(getAllUsersOptions())

const { isPending: getAllGroupsIsPending, data: groups } = useQuery(getAllGroupsOptions())

const usersFormated = computed(() => {
  if (!users.value) return [] as MultiSelectTagItemType[]
  return users.value.map((user) => ({
    id: user.id,
    label: user.name,
    avatar: user.photo
  })) as MultiSelectTagItemType[]
})

const groupsFormated = computed(() => {
  if (!groups.value) return [] as MultiSelectTagItemType[]
  return groups.value.map((group) => ({
    id: group.id,
    label: group.name,
    subLabel: group.category_name,
    icon: 'users-01'
  })) as MultiSelectTagItemType[]
})

const localName = ref(props.name)
const localDescription = ref(props.description)
const localVisibility = ref(props.visibility)
const localImage = ref(props.image)

watch(
  () => props.name,
  (value) => (localName.value = value)
)
watch(
  () => props.description,
  (value) => (localDescription.value = value)
)
watch(
  () => props.visibility,
  (value) => (localVisibility.value = value)
)
watch(
  () => props.image,
  (value) => (localImage.value = value)
)

watch(localName, (value) => emit('update:name', value))
watch(localDescription, (value) => emit('update:description', value))
watch(localVisibility, (value) => emit('update:visibility', value))
watch(localImage, (value) => emit('update:image', value))

const updateUsers = (users: MultiSelectTagItemType[]) => {
  emit('update:selectedUsers', users)
}

const updateGroups = (groups: MultiSelectTagItemType[]) => {
  emit('update:selectedGroups', groups)
}
</script>

<template>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-8 py-8 justify-between">
    <div class="flex flex-col gap-16">
      <div class="flex flex-col gap-4">
        <div>
          <h2 class="text-lg font-semibold text-gray-warm-900">
            {{ t('views.form-lab.info') }}
          </h2>
          <p class="text-sm text-gray-warm-600">
            {{ t('views.form-lab.description') }}
          </p>
        </div>
        <div>
          <Label>{{ t('views.form-lab.name') }} <span class="text-brand-700">*</span></Label>
          <Input
            v-model="localName"
            type="text"
            :placeholder="t('views.form-lab.name') + '*'"
            :disabled="disabled"
            required
          />
        </div>
      </div>

      <div>
        <h2 class="text-lg font-semibold text-gray-warm-900">
          {{ t('views.form-lab.visibility.title') }}
        </h2>
        <p class="text-sm text-gray-warm-700">
          {{ t('views.form-lab.visibility.info') }}
        </p>
        <div class="flex flex-row items-center mt-4 gap-2">
          <p class="text-gray-warm-700">
            {{ t('views.form-lab.visibility.toggle') }}
          </p>
          <Switch
            v-model="localVisibility"
            v-model:checked="localVisibility"
            :model-value="localVisibility"
            @update:model-value="localVisibility = $event"
          />
        </div>
      </div>
    </div>

    <div>
      <h2 class="text-lg font-semibold text-gray-warm-900 mb-2">
        {{ t('views.form-lab.preview.title') }}
      </h2>
      <p class="text-sm text-gray-600 mb-4">
        {{ t('views.form-lab.preview.info') }}
      </p>
      <CardPreview
        :title="localName"
        :description="localDescription"
        :custom-image="localImage"
        :disabled="disabled"
        @update:title="localName = $event"
        @update:description="localDescription = $event"
        @update:custom-image="localImage = $event"
      />
    </div>
  </div>

  <div class="mt-8">
    <div class="flex flex-row items-center gap-3">
      <h2 class="text-lg font-semibold text-gray-warm-900 mb-2">
        {{ t('views.form-lab.users.title') }}
      </h2>
      <Badge hierarchy="Info" size="md" icon="user-01" type="rounded">{{
        selectedUsers.length
      }}</Badge>
      <Badge hierarchy="Info" size="md" icon="users-01" type="rounded">{{
        selectedGroups.length
      }}</Badge>
    </div>
    <p class="text-sm text-gray-600 mb-4">
      {{
        t('views.form-lab.users.info', {
          users: selectedUsers.length,
          groups: selectedGroups.length
        })
      }}
    </p>
    <div class="flex flex-row gap-8 h-96">
      <MultiSelect
        :preselected-tags="selectedUsers"
        :tags="usersFormated"
        :label="t('views.form-lab.users.users')"
        placeholder="Search users"
        :loading="getAllUsersIsPending"
        :disabled="disabled"
        class="w-full"
        @update:selected-tags="updateUsers"
      />
      <Separator orientation="vertical" class="h-auto" />
      <MultiSelect
        :preselected-tags="selectedGroups"
        :tags="groupsFormated"
        :label="t('views.form-lab.users.groups')"
        placeholder="Search groups"
        :loading="getAllGroupsIsPending"
        :disabled="disabled"
        class="w-full"
        @update:selected-tags="updateGroups"
      />
    </div>
  </div>
</template>
