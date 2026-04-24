<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useMutation, useQuery } from '@tanstack/vue-query'

import Button from '@/components/ui/button/Button.vue'
import Icon from '@/components/icon/Icon.vue'
import LabFormSettings from '@/components/lab/LabFormSettings.vue'
import LabFormDesktops from '@/components/lab/LabFormDesktops.vue'
import UnsavedChangesModal from '@/components/modal/UnsavedChangesModal.vue'
import { Tab, TabsList, TabsContent } from '@/components/ui/tabs'
import TabsTrigger from '@/components/ui/tabs/TabsTrigger.vue'

import {
  editDeploymentApiV4ItemDeploymentDeploymentIdPutMutation,
  getLabApiV4ItemDeploymentLabLabIdGetOptions,
  getAllUsersApiV4ItemsUsersGetOptions,
  getAllGroupsApiV4ItemsGroupsGetOptions,
  getUserApiV4ItemUserGetOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { MultiSelectTagItemType } from '@/components/multi-select'

interface DesktopItem {
  id: number
  name: string
  description: string
  template: string | null
  hardware: Record<string, unknown>
  image: string
  guest_properties: Record<string, unknown>
  reservables: Record<string, unknown>
}

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const labId = Array.isArray(route.params.id) ? route.params.id[0] : route.params.id
const isSubmitting = ref(false)
const submitError = ref(null)
const showUnsavedChangesModal = ref(false)
const pendingNavigation = ref<(() => void) | null>(null)
const activeTab = ref('info')

const formData = ref({
  name: '',
  description: '',
  visibility: false,
  image: '',
  users: [] as MultiSelectTagItemType[],
  groups: [] as MultiSelectTagItemType[],
  desktops: [] as DesktopItem[]
})

const originalFormData = ref({})

const hasChanges = computed(() => {
  return JSON.stringify(formData.value) !== JSON.stringify(originalFormData.value)
})

const canAddNewDesktop = computed(() => {
  return formData.value.desktops.every((desktop) => desktop.template !== null)
})

const canSave = computed(() => {
  if (!formData.value.name || formData.value.name.trim() === '') {
    return false
  }
  if (formData.value.users.length === 0 && formData.value.groups.length === 0) {
    return false
  }
  if (formData.value.desktops.length === 0) {
    return false
  }
  const hasDesktopWithoutName = formData.value.desktops.some(
    (desktop) => !desktop.name || desktop.name.trim() === ''
  )
  if (hasDesktopWithoutName) {
    return false
  }
  return true
})

const getSaveButtonTooltip = computed(() => {
  if (canSave.value) return ''

  if (!formData.value.name || formData.value.name.trim() === '') {
    return t('views.form-lab.tooltip.enter-name')
  }

  if (formData.value.users.length === 0 && formData.value.groups.length === 0) {
    return t('views.form-lab.tooltip.select-users-or-groups')
  }

  if (formData.value.desktops.length === 0) {
    return t('views.form-lab.tooltip.add-desktop')
  }

  const hasDesktopWithoutName = formData.value.desktops.some(
    (desktop) => !desktop.name || desktop.name.trim() === ''
  )
  if (hasDesktopWithoutName) {
    return t('views.form-lab.tooltip.desktop-name-required')
  }

  return ''
})

const { data: currentUser } = useQuery(getUserApiV4ItemUserGetOptions())

const { isPending: getAllUsersIsPending, data: users } = useQuery(
  getAllUsersApiV4ItemsUsersGetOptions()
)

const { isPending: getAllGroupsIsPending, data: groups } = useQuery(
  getAllGroupsApiV4ItemsGroupsGetOptions()
)

const {
  data: lab,
  isPending,
  isError,
  error
} = useQuery(getLabApiV4ItemDeploymentLabLabIdGetOptions({ path: { lab_id: labId as string } }))

const editDeploymentMutation = useMutation(
  editDeploymentApiV4ItemDeploymentDeploymentIdPutMutation()
)

const transformFormDataToApiFormat = (data: {
  name: string
  description: string
  visibility: boolean
  image: string
  users: MultiSelectTagItemType[]
  groups: MultiSelectTagItemType[]
  desktops: DesktopItem[]
}) => {
  const userIds = data.users.map((user: MultiSelectTagItemType) => user.id)
  const groupIds = data.groups.map((group: MultiSelectTagItemType) => group.id)
  const createDict = data.desktops.map((desktop: DesktopItem) => {
    const apiHardware = {
      ...desktop.hardware,
      vcpus: desktop.hardware.cpu || desktop.hardware.vcpus,
      memory: desktop.hardware.ram || desktop.hardware.memory,
      boot_order: desktop.hardware.boot
        ? [desktop.hardware.boot]
        : desktop.hardware.boot_order || ['disk'],
      interfaces: desktop.hardware.networkInterfaces || desktop.hardware.interfaces || [],
      disk_bus: desktop.hardware.disk_bus,
      floppies: desktop.hardware.floppies || [],
      isos: desktop.hardware.isos || []
    }

    return {
      name: desktop.name,
      template: desktop.template,
      description: desktop.description || '',
      guest_properties: desktop.guest_properties,
      image: desktop.image,
      hardware: apiHardware,
      reservables: desktop.reservables
    }
  })

  return {
    name: data.name,
    description: data.description || '',
    kind: 'lab' as const,
    tag_visible: data.visibility,
    allowed: {
      users: userIds.length > 0 ? userIds : false,
      groups: groupIds.length > 0 ? groupIds : false,
      categories: false,
      roles: false
    },
    co_owners: [],
    resources: [],
    create_dict: createDict,
    image: {
      id: data.image ? data.image.split('/').pop() || '' : '',
      type: 'stock',
      url: data.image || ''
    },
    user: currentUser.value?.name || '',
    user_permissions: []
  }
}

const handleSave = async () => {
  try {
    isSubmitting.value = true
    submitError.value = null

    const apiData = transformFormDataToApiFormat(formData.value)
    await editDeploymentMutation.mutateAsync({
      path: { deployment_id: labId as string },
      body: apiData
    })

    router.push('/labs')
  } catch (error: unknown) {
    submitError.value =
      error instanceof Error ? error.message : 'An error occurred while updating the lab.'
  } finally {
    isSubmitting.value = false
  }
}

const handleCancel = () => {
  if (hasChanges.value) {
    pendingNavigation.value = () => router.push('/labs')
    showUnsavedChangesModal.value = true
  } else {
    router.push('/labs')
  }
}

const confirmDiscardChanges = () => {
  showUnsavedChangesModal.value = false
  if (pendingNavigation.value) {
    pendingNavigation.value()
    pendingNavigation.value = null
  }
}

const cancelDiscardChanges = () => {
  showUnsavedChangesModal.value = false
  pendingNavigation.value = null
}

// Desktop management functions
let desktopIdCounter = 0

const addDesktop = () => {
  if (!canAddNewDesktop.value) return
  const newDesktop: DesktopItem = {
    id: ++desktopIdCounter,
    name: '',
    description: '',
    template: null,
    hardware: {},
    image: '',
    guest_properties: {},
    reservables: {}
  }
  formData.value.desktops.push(newDesktop)
}

const updateDesktop = (id: number, key: string, value: unknown) => {
  const index = formData.value.desktops.findIndex((d) => d.id === id)
  if (index !== -1) {
    formData.value.desktops[index] = {
      ...formData.value.desktops[index],
      [key]: value
    }
  }
}

const deleteDesktop = (id: number) => {
  formData.value.desktops = formData.value.desktops.filter((d) => d.id !== id)
}

const parseLabData = (lab: Record<string, unknown>) => {
  if (lab?.create_dict?.length) {
    desktopIdCounter = lab.create_dict.length
  }

  const parsedLab = {
    ...lab,
    create_dict:
      (lab?.create_dict as Record<string, unknown>[] | undefined)?.map(
        (cd: Record<string, unknown>, index: number) => {
          const hw = cd.hardware as Record<string, unknown> | undefined
          return {
            ...cd,
            id: index + 1,
            hardware: {
              ...hw,
              ram: hw?.memory,
              cpu: hw?.vcpus,
              boot: (hw?.boot_order as string[] | undefined)?.[0],
              networkInterfaces: hw?.interfaces,
              isos: hw?.isos
            }
          }
        }
      ) || []
  }

  return parsedLab
}

const initializeFormData = (labData: Record<string, unknown>) => {
  if (!labData) return

  const parsed = parseLabData(labData)
  let mappedUsers: MultiSelectTagItemType[] = []
  let mappedGroups: MultiSelectTagItemType[] = []

  if (parsed.allowed?.users) {
    mappedUsers =
      parsed.allowed.users.map((userId: string) => {
        const user = (users.value as { id: string; name?: string; photo?: string }[])?.find(
          (u: { id: string; name?: string; photo?: string }) => u.id === userId
        )
        return {
          id: userId,
          label: user?.name || userId,
          avatar: user?.photo || ''
        }
      }) || []
  }

  if (parsed.allowed?.groups) {
    mappedGroups =
      parsed.allowed.groups.map((groupId: string) => {
        const group = (
          groups.value as { id: string; name?: string; category_name?: string }[]
        )?.find((g: { id: string; name?: string; category_name?: string }) => g.id === groupId)
        return {
          id: groupId,
          label: group?.name || groupId,
          subLabel: group?.category_name || '',
          icon: 'users-01'
        }
      }) || []
  }

  formData.value = {
    name: parsed.name || '',
    description: parsed.description || '',
    visibility: parsed.tag_visible || false,
    image: parsed.image?.url || '',
    users: mappedUsers,
    groups: mappedGroups,
    desktops: parsed.create_dict || []
  }

  originalFormData.value = JSON.parse(JSON.stringify(formData.value))
}

watch(
  [lab, users, groups],
  ([newLab, newUsers, newGroups]) => {
    if (newLab && newUsers && newGroups) {
      initializeFormData(newLab)
    }
  },
  { immediate: true }
)

window.addEventListener('beforeunload', (e) => {
  if (hasChanges.value) {
    e.preventDefault()
    e.returnValue = ''
  }
})
</script>

<template>
  <div class="flex flex-col w-full items-center gap-24 max-w-320">
    <Tab v-model="activeTab" class="w-full" default-value="info">
      <div class="w-full flex items-center justify-between gap-4">
        <div class="flex-1 flex">
          <TabsList
            class="border border-gray-warm-300 rounded-md gap-1 p-1 font-semibold bg-base-white"
          >
            <TabsTrigger
              value="info"
              class="justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow"
              @click="activeTab = 'info'"
            >
              {{ t('views.edit-lab.tabs.info') }}
            </TabsTrigger>
            <TabsTrigger
              value="desktops"
              class="justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow"
              @click="activeTab = 'desktops'"
            >
              {{ t('views.edit-lab.tabs.desktops') }}
            </TabsTrigger>
          </TabsList>
        </div>
        <div class="flex gap-2 absolute right-12 mt-40 lg:mt-auto">
          <Button hierarchy="secondary-gray" :disabled="isSubmitting" @click="handleCancel">
            {{ t('views.edit-lab.cancel') }}
          </Button>
          <Button
            hierarchy="primary"
            :disabled="isSubmitting || !canSave"
            :loading="isSubmitting"
            :title="getSaveButtonTooltip"
            @click="handleSave"
          >
            {{ t('views.edit-lab.save') }}
          </Button>
        </div>
      </div>

      <div
        v-if="isPending || getAllUsersIsPending || getAllGroupsIsPending"
        class="p-4 text-center"
      >
        <p class="text-gray-warm-600 flex items-center justify-center">
          <Icon name="loading-03" size="sm" class="animate-spin mr-2" />
          {{ t('views.edit-lab.loading-lab.data') }}
        </p>
      </div>

      <div v-else-if="isError" class="p-4 text-center">
        <div class="text-red-600 mb-4 p-2 bg-red-50 border border-red-200 rounded">
          {{ error?.message || 'Failed to load lab data' }}
        </div>
        <Button hierarchy="secondary-gray" @click="router.push('/labs')">
          {{ t('views.edit-lab.back-to-labs') }}
        </Button>
      </div>

      <div v-else-if="lab && users && groups" class="flex flex-col gap-8 w-full">
        <div
          v-if="submitError"
          class="text-error-600 mb-4 p-2 bg-red-50 border border-red-200 rounded"
        >
          {{ submitError }}
        </div>

        <TabsContent value="info" class="mt-6">
          <LabFormSettings
            :name="formData.name"
            :description="formData.description"
            :visibility="formData.visibility"
            :image="formData.image"
            :selected-users="formData.users"
            :selected-groups="formData.groups"
            @update:name="formData.name = $event"
            @update:description="formData.description = $event"
            @update:visibility="formData.visibility = $event"
            @update:image="formData.image = $event"
            @update:selected-users="formData.users = $event"
            @update:selected-groups="formData.groups = $event"
          />
        </TabsContent>

        <TabsContent value="desktops" class="mt-6">
          <LabFormDesktops
            :desktops="formData.desktops"
            @add-desktop="addDesktop"
            @update-desktop="updateDesktop"
            @delete-desktop="deleteDesktop"
          />
        </TabsContent>
      </div>
    </Tab>

    <UnsavedChangesModal
      :open="showUnsavedChangesModal"
      @confirm="confirmDiscardChanges"
      @cancel="cancelDiscardChanges"
    />
  </div>
</template>
