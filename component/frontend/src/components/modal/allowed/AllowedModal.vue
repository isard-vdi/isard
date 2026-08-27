<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { refDebounced } from '@vueuse/core'
import { useQuery } from '@tanstack/vue-query'
import { Modal } from '@/components/modal'
import { Button } from '@/components/ui/button'
import AllowedModalColumn from './AllowedModalColumn.vue'
import type { AllowedOption, AllowedSelection } from '.'
import type { AvailableUser } from '@/gen/oas/apiv4'
import {
  getAvailableGroupsForCategoryOptions,
  searchUsersInCategoryOptions,
  searchUsersInCategoryQueryKey,
  getDeploymentAllowedOptions,
  getDeploymentAllowedQueryKey,
  getMediaAllowedTableOptions,
  getMediaAllowedTableQueryKey,
  getTemplateAllowedOptions,
  getTemplateAllowedQueryKey,
  getUsersInGroupOptions,
  getUsersInGroupQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Checkbox } from '@/components/ui/checkbox'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { FeaturedIconOutline } from '@/components/icon/featured-outline/index.js'

interface Props {
  open: boolean
  loading?: boolean
  title?: string // Overrides the default title.
  description?: string // Overrides the description derived from itemType.
  warning?: string // Shown as an alert above the columns.
  itemId?: string // ID of the item being edited. Used to fetch current allowed settings.
  itemType?: 'template' | 'deployment' | 'media' // Type of the item being edited. Used to determine API endpoint and description.
  selection?: AllowedSelection // Selection to open with when the item does not exist yet
  requireSelection?: boolean // Block saving if the selection is empty
  supportsEveryone?: boolean // Whether an empty array means "everyone"
  usersOnly?: boolean // Only users can be picked; groups become browse-only navigation
  roles?: string[] // Restrict the pickable users to these role ids
  preselectedUsers?: AllowedOption[] // Users shown in the users column when nothing is being browsed or searched
  error?: string // Error message to show in the footer.
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  loading: false,
  title: '',
  description: '',
  warning: '',
  itemId: undefined,
  itemType: undefined,
  selection: undefined,
  requireSelection: false,
  supportsEveryone: true,
  usersOnly: false,
  roles: undefined,
  preselectedUsers: undefined,
  error: ''
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', selection: AllowedSelection): void
}>()

const { t } = useI18n()

const everyoneEnabled = computed(() => props.supportsEveryone && !props.usersOnly)

const roleQuery = computed(() => (props.roles?.length ? { roles: [...props.roles] } : undefined))

// --- Queries ---------------------------------------------------------------

const templateId = computed(() => (props.itemType === 'template' ? (props.itemId ?? '') : ''))
const mediaId = computed(() => (props.itemType === 'media' ? (props.itemId ?? '') : ''))
const deploymentId = computed(() => (props.itemType === 'deployment' ? (props.itemId ?? '') : ''))

const {
  data: templateAllowed,
  isPending: templateIsPending,
  error: templateError
} = useQuery({
  ...getTemplateAllowedOptions({ path: { template_id: templateId.value } }),
  queryKey: computed(() => getTemplateAllowedQueryKey({ path: { template_id: templateId.value } })),
  enabled: computed(() => props.open && !!templateId.value)
})

const {
  data: mediaAllowed,
  isPending: mediaIsPending,
  error: mediaError
} = useQuery({
  ...getMediaAllowedTableOptions({ path: { media_id: mediaId.value } }),
  queryKey: computed(() => getMediaAllowedTableQueryKey({ path: { media_id: mediaId.value } })),
  enabled: computed(() => props.open && !!mediaId.value)
})

const {
  data: deploymentAllowed,
  isPending: deploymentIsPending,
  error: deploymentError
} = useQuery({
  ...getDeploymentAllowedOptions({ path: { deployment_id: deploymentId.value } }),
  queryKey: computed(() =>
    getDeploymentAllowedQueryKey({ path: { deployment_id: deploymentId.value } })
  ),
  enabled: computed(() => props.open && !!deploymentId.value)
})

const categoryGroups = useQuery({
  ...getAvailableGroupsForCategoryOptions(),
  enabled: computed(() => props.open && !templateId.value && !mediaId.value && !deploymentId.value)
})

const allowedData = computed(() => {
  if (templateId.value) return templateAllowed.value
  if (mediaId.value) return mediaAllowed.value
  if (deploymentId.value) return deploymentAllowed.value
  return undefined
})

const allowedIsPending = computed(() => {
  if (templateId.value) return templateIsPending.value
  if (mediaId.value) return mediaIsPending.value
  if (deploymentId.value) return deploymentIsPending.value
  return categoryGroups.isPending.value
})

const allowedError = computed(() => {
  if (templateId.value) return templateError.value
  if (mediaId.value) return mediaError.value
  if (deploymentId.value) return deploymentError.value
  return categoryGroups.error.value
})

// --- Selection state -------------------------------------------------------

const selectedGroups = ref<string[]>([])
const selectedUsers = ref<string[]>([])
const apiIndeterminateGroups = ref<string[]>([])
const apiAllGroups = ref(false)

const shareWithEveryone = ref(false)
const usersByGroup = ref<Record<string, AllowedOption[]>>({})

const viewedGroup = ref<string | null>(null)
const groupSearch = ref('')
const userSearch = ref('')

const hydrated = ref(false)
const dirty = ref(false)

watch(
  () => props.open,
  (open) => {
    if (open) return

    hydrated.value = false
    dirty.value = false
    selectedGroups.value = []
    selectedUsers.value = []
    apiIndeterminateGroups.value = []
    apiAllGroups.value = false
    shareWithEveryone.value = false
    viewedGroup.value = null
    groupSearch.value = ''
    userSearch.value = ''
  }
)

// --- Groups column ---------------------------------------------------------

const expectsApiState = computed(
  () => !!templateId.value || !!mediaId.value || !!deploymentId.value
)

const availableGroups = computed<AllowedOption[]>(() => {
  const groups = expectsApiState.value
    ? allowedData.value?.available_groups
    : categoryGroups.data.value?.available_groups
  if (!Array.isArray(groups)) return []
  return groups.map((group) => ({
    value: group.id,
    label: group.name,
    subLabel: group.description ?? undefined
  }))
})

const readBucket = (value: boolean | string[] | undefined, all: () => string[]): string[] => {
  if (!Array.isArray(value)) return []
  if (value.length === 0) return everyoneEnabled.value ? all() : []
  return [...value]
}

const hydrate = () => {
  if (expectsApiState.value && !allowedData.value) return
  const source = props.selection ?? allowedData.value?.selected
  if (!source) return

  const allGroupIds = () => availableGroups.value.map((group) => group.value)

  if (
    everyoneEnabled.value &&
    Array.isArray(source.groups) &&
    source.groups.length === 0 &&
    allGroupIds().length === 0
  ) {
    return
  }

  selectedGroups.value = readBucket(source.groups, allGroupIds)

  apiAllGroups.value =
    everyoneEnabled.value && Array.isArray(source.groups) && source.groups.length === 0
  shareWithEveryone.value =
    everyoneEnabled.value && Array.isArray(source.users) && source.users.length === 0
  selectedUsers.value =
    !shareWithEveryone.value && Array.isArray(source.users) ? [...source.users] : []
  apiIndeterminateGroups.value = Array.isArray(allowedData.value?.indeterminate_groups)
    ? allowedData.value.indeterminate_groups.map((group) => group.id)
    : []
  hydrated.value = true
}

watch(
  [() => props.open, () => props.selection, allowedData, availableGroups],
  () => {
    if (props.open && !hydrated.value) hydrate()
  },
  { immediate: true }
)

const indeterminateGroups = computed(() => {
  const ids = new Set(apiIndeterminateGroups.value)

  for (const [groupId, members] of Object.entries(usersByGroup.value)) {
    if (members.some((member) => selectedUsers.value.includes(member.value))) {
      ids.add(groupId)
    } else {
      ids.delete(groupId)
    }
  }
  for (const groupId of selectedGroups.value) ids.delete(groupId)
  return [...ids]
})

const groupsEmptyText = computed(() =>
  allowedError.value ? t('api.loading-error') : t('components.allowed-modal.empty.groups')
)

// Counted against availableGroups so it always matches what the column considers selected.
const selectedGroupCount = computed(() => {
  const selected = new Set(selectedGroups.value)
  return availableGroups.value.filter((group) => selected.has(group.value)).length
})

// --- Users column ----------------------------------------------------------

const usersInGroup = useQuery({
  ...getUsersInGroupOptions({
    path: { group_id: viewedGroup.value ?? '' },
    query: roleQuery.value
  }),
  queryKey: computed(() =>
    getUsersInGroupQueryKey({
      path: { group_id: viewedGroup.value ?? '' },
      query: roleQuery.value
    })
  ),
  enabled: computed(() => props.open && !!viewedGroup.value)
})

const MIN_TERM_LENGTH = 2

const userTerm = computed(() => userSearch.value.trim())
const debouncedUserTerm = refDebounced(userTerm, 250)

const termSearchActive = computed(
  () => !viewedGroup.value && debouncedUserTerm.value.length >= MIN_TERM_LENGTH
)

const USER_SEARCH_LIMIT = 50

const searchedUsers = useQuery({
  ...searchUsersInCategoryOptions({
    query: { search: debouncedUserTerm.value, limit: USER_SEARCH_LIMIT, ...roleQuery.value }
  }),
  queryKey: computed(() =>
    searchUsersInCategoryQueryKey({
      query: { search: debouncedUserTerm.value, limit: USER_SEARCH_LIMIT, ...roleQuery.value }
    })
  ),
  enabled: computed(() => props.open && termSearchActive.value)
})

const toOption = (user: AvailableUser): AllowedOption => ({
  value: user.id,
  label: user.name || user.username,
  subLabel: user.username,
  avatar: user.photo ?? ''
})

const searchedUserOptions = computed<AllowedOption[]>(() =>
  (searchedUsers.data.value?.users ?? []).map(toOption)
)

watch(
  () => usersInGroup.data.value,
  (data) => {
    const groupId = viewedGroup.value
    if (!groupId || !Array.isArray(data?.users)) return
    usersByGroup.value = {
      ...usersByGroup.value,
      [groupId]: data.users.map(toOption)
    }
  },
  { immediate: true }
)

const viewedGroupUsers = computed<AllowedOption[]>(() =>
  viewedGroup.value ? (usersByGroup.value[viewedGroup.value] ?? []) : []
)

const viewedGroupName = computed(
  () => availableGroups.value.find((group) => group.value === viewedGroup.value)?.label ?? ''
)

const checkedUsers = computed(() => {
  if (viewedGroup.value && selectedGroups.value.includes(viewedGroup.value)) {
    return viewedGroupUsers.value.map((user) => user.value)
  }
  return selectedUsers.value
})

const knownUsers = computed<Record<string, AllowedOption>>(() => {
  const known: Record<string, AllowedOption> = {}
  for (const user of props.preselectedUsers ?? []) known[user.value] = user
  for (const members of Object.values(usersByGroup.value)) {
    for (const member of members) known[member.value] = member
  }
  for (const user of searchedUserOptions.value) known[user.value] = user
  return known
})

const showsSelectionWhenIdle = computed(() => props.preselectedUsers !== undefined)

const idleUserOptions = computed<AllowedOption[]>(() => {
  const options = [...(props.preselectedUsers ?? [])]
  const seen = new Set(options.map((option) => option.value))
  for (const id of selectedUsers.value) {
    if (seen.has(id)) continue
    const option = knownUsers.value[id]
    if (!option) continue
    options.push(option)
    seen.add(id)
  }
  return options
})

const usersColumnItems = computed<AllowedOption[]>(() => {
  if (viewedGroup.value) return viewedGroupUsers.value
  if (termSearchActive.value) return searchedUserOptions.value
  return showsSelectionWhenIdle.value ? idleUserOptions.value : []
})

const usersLoading = computed(() => {
  if (viewedGroup.value) {
    return usersInGroup.isPending.value && viewedGroupUsers.value.length === 0
  }
  return termSearchActive.value && searchedUsers.isFetching.value
})

const searchSettled = computed(() => debouncedUserTerm.value === userTerm.value)

const usersFooterText = computed(() => {
  if (viewedGroup.value || !termSearchActive.value) return ''
  if (usersLoading.value || !searchSettled.value) return ''
  const shown = searchedUserOptions.value.length
  const total = searchedUsers.data.value?.total ?? 0
  if (shown === 0 || total <= shown) return ''
  return t('components.allowed-modal.search.user.truncated', { shown, total })
})

const usersColumnTitle = computed(() =>
  viewedGroup.value
    ? t('components.allowed-modal.columns.users-in-group', { group_name: viewedGroupName.value })
    : t('components.allowed-modal.columns.users')
)

const userSearchPlaceholder = computed(() =>
  viewedGroup.value
    ? t('components.allowed-modal.search.user-in-group.placeholder', {
        group_name: viewedGroupName.value
      })
    : t('components.allowed-modal.search.user.placeholder')
)

const usersEmptyText = computed(() => {
  if (viewedGroup.value) {
    if (usersInGroup.error.value) return t('api.loading-error')
    return t('components.allowed-modal.empty.users')
  }
  if (userTerm.value.length > 0 && userTerm.value.length < MIN_TERM_LENGTH) {
    return t('components.allowed-modal.empty.no-group-short-term')
  }
  if (searchedUsers.error.value) return t('api.loading-error')
  if (termSearchActive.value && !searchedUsers.isFetching.value) {
    return t('components.allowed-modal.search.user.empty')
  }
  if (showsSelectionWhenIdle.value) {
    return t('components.allowed-modal.empty.no-users-selected')
  }
  return t('components.allowed-modal.empty.no-group')
})

// --- Handlers --------------------------------------------------------------

const viewGroup = (groupId: string) => {
  viewedGroup.value = viewedGroup.value === groupId ? null : groupId
  userSearch.value = ''
}

const dropKnownMembers = (groupIds: string[]) => {
  const memberIds = new Set(
    groupIds.flatMap((id) => (usersByGroup.value[id] ?? []).map((member) => member.value))
  )
  if (memberIds.size === 0) return
  selectedUsers.value = selectedUsers.value.filter((id) => !memberIds.has(id))
}

const toggleAllGroups = (selectAll: boolean) => {
  if (props.usersOnly) return
  dirty.value = true
  const groupIds = availableGroups.value.map((group) => group.value)
  apiAllGroups.value = everyoneEnabled.value && selectAll
  selectedGroups.value = selectAll ? groupIds : []
  dropKnownMembers(groupIds)
}

const toggleGroup = (groupId: string) => {
  if (props.usersOnly) return
  dirty.value = true
  apiAllGroups.value = false
  selectedGroups.value = selectedGroups.value.includes(groupId)
    ? selectedGroups.value.filter((id) => id !== groupId)
    : [...selectedGroups.value, groupId]
  dropKnownMembers([groupId])
}

const toggleUser = (userId: string) => {
  dirty.value = true
  const groupId = viewedGroup.value

  if (!groupId) {
    shareWithEveryone.value = false
    selectedUsers.value = selectedUsers.value.includes(userId)
      ? selectedUsers.value.filter((id) => id !== userId)
      : [...selectedUsers.value, userId]
    return
  }

  shareWithEveryone.value = false

  const users = [...selectedUsers.value]
  if (selectedGroups.value.includes(groupId)) {
    apiAllGroups.value = false
    selectedGroups.value = selectedGroups.value.filter((id) => id !== groupId)
    for (const member of viewedGroupUsers.value) {
      if (!users.includes(member.value)) users.push(member.value)
    }
  }

  selectedUsers.value = users.includes(userId)
    ? users.filter((id) => id !== userId)
    : [...users, userId]
}

const toggleShareWithEveryone = () => {
  if (props.loading) return
  dirty.value = true
  shareWithEveryone.value = !shareWithEveryone.value
}

const isEmptySelection = computed(() => {
  if (props.usersOnly) return selectedUsers.value.length === 0
  return (
    !shareWithEveryone.value &&
    !apiAllGroups.value &&
    selectedGroups.value.length === 0 &&
    selectedUsers.value.length === 0
  )
})

const requireSelectionText = computed(() =>
  props.usersOnly
    ? t('components.allowed-modal.require-selection-users')
    : t('components.allowed-modal.require-selection')
)

const columnsDisabled = computed(() => shareWithEveryone.value || props.loading)

const saveDisabled = computed(
  () => props.loading || !dirty.value || (props.requireSelection && isEmptySelection.value)
)

const saveHint = computed(() =>
  !props.loading && !dirty.value ? t('components.allowed-modal.no-changes') : ''
)

const handleSave = () => {
  if (saveDisabled.value) return
  emit('save', {
    groups: props.usersOnly
      ? false
      : shareWithEveryone.value
        ? false
        : apiAllGroups.value
          ? []
          : selectedGroups.value.length
            ? [...selectedGroups.value]
            : false,
    users: shareWithEveryone.value
      ? []
      : selectedUsers.value.length
        ? [...selectedUsers.value]
        : false
  })
}

const handleClose = () => {
  emit('close')
}
</script>

<template>
  <Modal
    :open="props.open"
    :title="props.title || t('components.allowed-modal.title')"
    :description="
      props.description ||
      t(
        `components.allowed-modal.description.${props.itemType}`,
        t('components.allowed-modal.description.generic')
      )
    "
    size="4xl"
    :close-on-backdrop-click="false"
    @close="handleClose"
  >
    <div v-if="props.warning" class="mb-4 w-full flex justify-center">
      <Alert variant="warning" class="w-[min(100%,var(--spacing-256))]">
        <FeaturedIconOutline kind="outline" color="warning" />
        <AlertTitle class="font-bold text-gray-warm-700 mb-2">{{
          t('components.allowed-modal.warning')
        }}</AlertTitle>
        <AlertDescription>{{ props.warning }}</AlertDescription>
      </Alert>
    </div>
    <div
      v-if="everyoneEnabled"
      :class="[
        'mb-4 flex shrink-0 select-none flex-row items-center gap-2 rounded-lg border p-3',
        shareWithEveryone ? 'border-brand-600 bg-brand-100' : 'border-gray-warm-200 bg-base-white',
        props.loading ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
        !props.loading && !shareWithEveryone && 'hover:bg-gray-warm-50'
      ]"
      data-slot="share-everyone"
      @click="toggleShareWithEveryone"
    >
      <FeaturedIconOutline kind="filled" color="brand" name="users-02" />
      <div class="flex min-w-0 flex-col mr-auto">
        <span class="text-sm font-semibold text-gray-warm-700">
          {{
            t(
              `components.allowed-modal.share-everyone.${shareWithEveryone ? 'checked' : 'unchecked'}.title`
            )
          }}
        </span>
        <span class="text-sm font-normal text-gray-warm-600">
          {{
            t(
              `components.allowed-modal.share-everyone.${shareWithEveryone ? 'checked' : 'unchecked'}.description`
            )
          }}
        </span>
      </div>
      <span class="flex shrink-0 items-center justify-center p-3" @click.stop>
        <Checkbox
          :model-value="shareWithEveryone"
          :aria-label="
            t(
              `components.allowed-modal.share-everyone.${shareWithEveryone ? 'checked' : 'unchecked'}.title`
            )
          "
          :disabled="props.loading"
          data-slot="share-everyone-checkbox"
          size="md"
          class="bg-base-white"
          @update:model-value="toggleShareWithEveryone"
        />
      </span>
    </div>

    <div class="flex h-[60vh] max-h-[480px] min-h-[320px] gap-6">
      <AllowedModalColumn
        v-model:search="groupSearch"
        :title="t('components.allowed-modal.columns.groups')"
        :items="availableGroups"
        :selected="selectedGroups"
        :indeterminate="indeterminateGroups"
        :active-id="viewedGroup"
        :loading="allowedIsPending"
        :disabled="columnsDisabled"
        :search-placeholder="t('components.allowed-modal.search.group.placeholder')"
        :empty-text="groupsEmptyText"
        :not-found-text="t('components.allowed-modal.search.group.empty')"
        :selectable="!props.usersOnly"
        :select-all="everyoneEnabled"
        :select-all-checked="apiAllGroups"
        :select-all-label="t('components.allowed-modal.select-all.groups')"
        :select-all-count-label="
          t('components.allowed-modal.select-all.count', {
            selected: selectedGroupCount,
            total: availableGroups.length
          })
        "
        @toggle="toggleGroup"
        @toggle-all="toggleAllGroups"
        @select="viewGroup"
      >
        <template #actions="{ item }">
          <Button
            :icon="item.value === viewedGroup ? 'minus-circle' : 'arrow-circle-broken-right'"
            hierarchy="link-color"
            :aria-label="
              item.value === viewedGroup
                ? t('components.allowed-modal.unview-group', { group_name: item.label })
                : t('components.allowed-modal.view-group', { group_name: item.label })
            "
            @click.stop="viewGroup(item.value)"
          />
        </template>
      </AllowedModalColumn>

      <AllowedModalColumn
        v-model:search="userSearch"
        :title="usersColumnTitle"
        :items="usersColumnItems"
        :selected="checkedUsers"
        :loading="usersLoading"
        :disabled="columnsDisabled"
        :search-placeholder="userSearchPlaceholder"
        :empty-text="usersEmptyText"
        :not-found-text="t('components.allowed-modal.search.user.empty')"
        :footer-text="usersFooterText"
        @toggle="toggleUser"
        @select="toggleUser"
      />
    </div>

    <div v-if="props.error" class="mt-4 w-full flex justify-center">
      <Alert variant="destructive" class="w-[min(100%,var(--spacing-256))]">
        <AlertDescription>{{ props.error }}</AlertDescription>
      </Alert>
    </div>

    <template #footer>
      <div class="flex w-full items-center justify-end gap-4">
        <p
          v-if="props.requireSelection && isEmptySelection"
          class="min-w-0 truncate text-sm text-gray-warm-600"
        >
          {{ requireSelectionText }}
        </p>
        <div class="flex shrink-0 gap-2">
          <Button hierarchy="secondary-gray" :disabled="props.loading" @click="handleClose">
            {{ t('components.allowed-modal.cancel') }}
          </Button>
          <Tooltip :disabled="!saveHint">
            <TooltipTrigger as-child>
              <span class="flex">
                <Button
                  :disabled="saveDisabled"
                  :icon="props.loading ? 'loading-02' : ''"
                  icon-class="motion-safe:animate-[spin_2s_linear_infinite]"
                  :class="saveDisabled && 'pointer-events-none'"
                  @click="handleSave"
                >
                  {{ t('components.allowed-modal.save') }}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent v-if="saveHint" :title="saveHint" />
          </Tooltip>
        </div>
      </div>
    </template>
  </Modal>
</template>
