<script setup lang="ts">
import { Modal } from '@/components/modal'
import { useI18n } from 'vue-i18n'
import { AllowedModalSelectedItem } from '.'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { ref, computed, watch } from 'vue'
import { type Option, MultiSelect } from '@/components/multi-select'
import { Button } from '@/components/ui/button'
import { useQuery } from '@tanstack/vue-query'
import { InputField } from '@/components/input-field'
import {
  getAvailableGroupsForCategoryOptions,
  getUsersInGroupOptions,
  getTemplateAllowedOptions,
  getMediaAllowedTableOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

interface Props {
  open: boolean
  loading?: boolean
  title?: string
  description?: string
  itemId?: string // ID of the item being edited. Used to fetch current allowed settings.
  itemType?: 'template' | 'deployment' | 'media' // Type of the item being edited. Used to determine API endpoint.
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  loading: false,
  title: '',
  description: ''
})

const { t } = useI18n()

// If no itemId or itemType is provided, we cannot fetch the allowed item field
// Hence show the available groups and users as empty lists
let allowedLoading, allowedError, allowedData;

if (props.itemType === 'template') {
  ({ 
    isPending: allowedLoading,
    error: allowedError,
    data: allowedData
  } = useQuery({
    ...getTemplateAllowedOptions({
      path: {
        template_id: props.itemId!
      }
    }),
    enabled: computed(() => !!props.itemId && props.itemType === 'template')
  }));
} else if (props.itemType === 'media') {
  ({
    isPending: allowedLoading,
    error: allowedError,
    data: allowedData
  } = useQuery({
    ...getMediaAllowedTableOptions({
      path: {
        media_id: props.itemId!
      }
    }),
    enabled: computed(() => !!props.itemId && props.itemType === 'media')
  }));
} else {
  console.warn('No itemType or unsupported itemType provided, fetching available groups only');
  ({
    isPending: allowedLoading,
    error: allowedError,
    data: allowedData
  } = useQuery({
    ...getAvailableGroupsForCategoryOptions(),
    enabled: computed(() => !!props.open)
  }));
}

// Available groups for selection. This is fetched from the API and may include additional info like subLabel, etc.
const availableGroups = computed<Option[]>(() => {
  if (!allowedData.value?.available_groups) return []
  if (!Array.isArray(allowedData.value.available_groups)) return []
  return allowedData.value.available_groups.map((group: any) => ({
    label: group.name,
    value: group.id,
    subLabel: group.description
  }))
})


// Selection and search states
const currentGroup  = ref<string | null>(null)
const groupSearch = ref('')
const userSearch = ref('')

// Selected groups and users (checkbox states)
const selectedGroups = ref<string[]>([])
const selectedUsers = ref<string[]>([])

// Users fetched from the selected group
const groupUsers = ref<Option[]>([])


// Handlers for selecting groups (checkbox) and viewing group users (button click)
const handleSelectGroup = async (groupId: string) => {
  console.log('Selected group:', groupId)
  selectedGroups.value.push(groupId)
  userSearch.value = ''
}

const handleViewGroup = (groupId: string) => {
  console.log('View group details for:', groupId)
  // Fetch the users in the group and show in the right column
  currentGroup.value = groupId
  console.log('Current group set to:', currentGroup.value)
}

// Fetch group users when a group is selected
const {
  isPending: usersLoading,
  error: usersError,
  data: usersData
} = useQuery({
  ...getUsersInGroupOptions({
    path: {
      group_id: computed(() => currentGroup.value!)
    }
  }),
  enabled: computed(() => !!currentGroup.value)
})


// Watch for usersData changes
watch(usersData, (val) => {
  groupUsers.value = Array.isArray(val)
    ? val.map((user: any) => ({
        label: user.label ?? user.name ?? user.username ?? '',
        value: user.value ?? user.id ?? user.username ?? '',
        subLabel: user.subLabel ?? user.email ?? undefined,
        avatar: user.avatar ?? undefined,
        icon: user.icon ?? undefined
      }))
    : []
})


const filteredGroups = computed(() => {
  return availableGroups.value.filter(g =>
    g.label.toLowerCase().includes(groupSearch.value.toLowerCase()) ||
    g.subLabel?.toLowerCase().includes(groupSearch.value.toLowerCase())
  )
})

const filteredUsers = computed(() => {
  if (!currentGroup.value) return []
  if (userSearch.value === '') {
    return groupUsers.value
  }
  return groupUsers.value.filter(u =>
    u.label.toLowerCase().includes(userSearch.value.toLowerCase()) ||
    u.subLabel?.toLowerCase().includes(userSearch.value.toLowerCase())
  )
})

const searchUserPlaceholder = computed(() => {
  return currentGroup.value
    ? t('components.allowed-modal.search.user.placeholder', { group_name: currentGroup.value })
    : t('components.allowed-modal.search.user.placeholder')
})


// const deleteItem = (removedValue: string) => {
//   console.log('deleting', removedValue)
//   console.log('multiple?', props.multiple)
//   if (props.multiple) {
//     console.log('current modelValue', modelValue.value)
//     const current = Array.isArray(modelValue.value) ? [...modelValue.value] : []
//     const newValues = current.filter((v) => v !== removedValue)
//     console.log('newValues', newValues)
//     modelValue.value = newValues
//     console.log('updated modelValue', modelValue.value)
//   } else {
//     modelValue.value = ''
//   }
// }

// Save and close

const emit = defineEmits(['close', 'save'])

const handleSave = () => {
  // TODO: Gather selected groups and users to emit
  // emit('save', selected.value)
  emit('close')
}

const handleClose = () => {
  emit('close')
}

</script>
<template>
  <Modal
    :open="props.open"
    :loading="props.loading"
    :title="props.title"
    :description="props.description"
    @close="handleClose"
    @save="handleSave"
    size="4xl"
    class="h-[600px]"
  >
    <template #default>
      <div class="flex gap-4">
        <!-- Groups Column -->
        <div class="flex-1 flex flex-col">
          <InputField
            v-model="groupSearch"
            :placeholder="t('components.allowed-modal.search.group.placeholder')"
          />
          <ScrollArea class="h-full bg-transparent rounded-md">
            <div v-if="props.loading" class="flex flex-col gap-2">
              <Skeleton class="h-6" />
              <Skeleton class="h-6" />
              <Skeleton class="h-6" />
            </div>
            <div v-else class="flex flex-col gap-1">
              <AllowedModalSelectedItem
              v-for="group in filteredGroups"
              :key="group.value"
              :label="group.label"
              :sub-label="group.subLabel"
              :value="group.value"
              @update:checked="handleSelectGroup(group.value)"
              class="flex items-center justify-between"
              >
              <template #actions>
                <div class="ml-auto flex items-center">
                  <Button
                  @click="handleViewGroup(group.value)"
                  icon="arrow-circle-broken-right"
                  hierarchy="link-color"
                />
                </div>
              </template>
              </AllowedModalSelectedItem>
            </div>
          </ScrollArea>
        </div>
        <!-- Users Column -->
        <div class="flex-1 flex flex-col">
          <p>Selected Group: {{ currentGroup }}</p>
          {{  groupUsers }}
          {{ filteredUsers }}
          <MultiSelect
            :model-value="selectedUsers"
            :options="filteredUsers"
            :searchable="true"
            :search-value="groupSearch"
            @update:search-value="(val) => (groupSearch = val)"
            :placeholder="searchUserPlaceholder"
            :label="''"
            size="lg"
          />
          <ScrollArea class="h-full bg-transparent rounded-md">
            <div v-if="props.loading" class="flex flex-col gap-2">
              <Skeleton class="h-6" />
              <Skeleton class="h-6" />
              <Skeleton class="h-6" />
            </div>
            <div v-else class="flex flex-col gap-1">
              <AllowedModalSelectedItem
                v-for="user in filteredUsers"
                :key="user.value"
                :label="user.label"
                :sub-label="user.subLabel"
                :value="user.value"
                :avatar="user.avatar"
                :icon="user.icon"
              />
            </div>
          </ScrollArea>
        </div>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <Button
          class="btn btn-secondary-2"
          @click="handleClose"
          :disabled="props.loading"
          hierarchy="secondary-gray"
        >
          {{ t('components.allowed-modal.cancel') }}
        </Button>
        <Button
          class="btn btn-primary-500"
          @click="handleSave"
          :disabled="props.loading"
        >
          {{ t('components.allowed-modal.save') }}
        </Button>
      </div>
    </template>
  </Modal>

</template>