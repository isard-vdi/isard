<script setup lang="ts">
import { computed, ref, toRaw, type HTMLAttributes } from 'vue'
import { TabsRoot, TabsList, TabsTrigger } from 'radix-vue'
import Button from '@/components/ui/button/Button.vue'
import Modal from '@/components/modal/Modal.vue'
import Input from '@/components/ui/input/Input.vue'
import Icon from '@/components/icon/Icon.vue'
import Select from '@/components/ui/select/Select.vue'
import TemplateListItem from '@/components/template-list-item/TemplateListItem.vue'
import ImageSelectModal from '@/components/image/ImageSelectModal.vue'

import mountains from '@/assets/img/mountains.svg'
import { useI18n } from 'vue-i18n'

interface IsoObject {
  id: string
  name?: string
}

interface TemplateItem {
  id: string
  name: string
  description?: string
  image?: { id?: string; type?: string; url?: string }
  user_name?: string
  guest_properties?: Record<string, unknown>
  create_dict: {
    hardware: {
      vcpus?: number
      memory?: number
      boot_order?: string[]
      interfaces?: string[]
      isos?: (string | IsoObject)[]
      [key: string]: unknown
    }
    reservables?: { vgpus?: string[] }
    [key: string]: unknown
  }
  [key: string]: unknown
}

interface Props {
  number: number
  name: string
  description?: string
  image?: string
  hardware: {
    cpu: number
    ram: number
    boot: string
    isos: (string | IsoObject)[]
    networkInterfaces: string[]
  }
  templates: TemplateItem[]
  isTemplatesLoading: boolean
  isTemplatesError: boolean
  templateSearchTerm: string
  activeTemplateTab: string
}

const props = defineProps<Props>()
const emit = defineEmits([
  'update:name',
  'update:description',
  'update:image',
  'update:hardware',
  'update:guest_properties',
  'update:templateSearchTerm',
  'update:activeTemplateTab',
  'update:template',
  'delete'
])

const { t } = useI18n()
const isExpanded = ref(true)
const isTemplateModalOpen = ref(false)
const isHardwareModalOpen = ref(false)
const showImageModal = ref(false)

const localName = ref(props.name)
const localDescription = ref(props.description || '')
const localImage = ref(
  typeof props.image === 'string'
    ? { id: props.image.split('/').pop() || '', type: 'stock', url: props.image }
    : props.image || { id: '', type: 'stock', url: '' }
)
const localHardware = ref({ ...props.hardware })

const tempHardware = ref({ ...props.hardware })

const localTemplateSearchTerm = computed({
  get: () => props.templateSearchTerm,
  set: (value) => emit('update:templateSearchTerm', value)
})

const localActiveTab = computed({
  get: () => props.activeTemplateTab,
  set: (value) => emit('update:activeTemplateTab', value)
})

const selectedTemplateId = ref(null)
const selectedTemplateHardware = ref(null)

// Temporary fix: prevent selection of templates with reservables.vgpus until deployments can be booked
const hasReservableVgpus = (template: TemplateItem) => {
  return (
    template?.create_dict?.reservables?.vgpus &&
    Array.isArray(template.create_dict.reservables.vgpus) &&
    template.create_dict.reservables.vgpus.length > 0
  )
}

const selectTemplate = (template: TemplateItem) => {
  // Temporary fix until deployments can be booked
  if (hasReservableVgpus(template)) {
    return
  }

  selectedTemplateId.value = template.id
  selectedTemplateHardware.value = template.create_dict

  const hardware = {
    ...template.create_dict.hardware,
    cpu: template.create_dict.hardware.vcpus,
    ram: template.create_dict.hardware.memory, // kB
    boot: template.create_dict.hardware.boot_order?.[0] || 'disk',
    networkInterfaces: template.create_dict.hardware.interfaces || [],
    isos: template.create_dict.hardware.isos || []
  }
  localHardware.value = hardware
  emit('update:hardware', hardware)

  if (template.image && template.image.url) {
    localImage.value = {
      id: template.image.id || '',
      type: template.image.type || 'stock',
      url: template.image.url
    }
    emit('update:image', localImage.value)
  }

  if (!localName.value.trim()) {
    localName.value = template.name
    updateName()
  }

  if (!localDescription.value.trim()) {
    localDescription.value = template.description || ''
    updateDescription()
  }

  if (template.guest_properties) {
    emit('update:guest_properties', template.guest_properties)
  }
  emit('update:template', template.id)
}

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const openTemplateModal = () => {
  isTemplateModalOpen.value = true
}

const openHardwareModal = () => {
  tempHardware.value = { ...localHardware.value }
  isHardwareModalOpen.value = true
}

const saveHardwareChanges = () => {
  localHardware.value = { ...tempHardware.value }
  emit('update:hardware', localHardware.value)
  isHardwareModalOpen.value = false
}

const updateName = () => {
  emit('update:name', localName.value)
}

const updateDescription = () => {
  emit('update:description', localDescription.value)
}

const deleteDesktop = () => {
  emit('delete')
}

const changeImage = () => {
  showImageModal.value = true
}

const handleImageSelected = (img: string) => {
  localImage.value = { id: img.split('/').pop() || '', type: 'stock', url: img }
  emit('update:image', localImage.value)
}

const isTemplateSelected = computed(() => {
  return localHardware.value.cpu > 0 && localHardware.value.ram > 0
})

const displayIsos = computed(() => {
  if (!localHardware.value.isos || localHardware.value.isos.length === 0) {
    return '--'
  }

  return localHardware.value.isos
    .map((iso) => {
      if (typeof iso === 'object' && iso !== null) {
        const isoObj = iso as IsoObject
        return isoObj.name || isoObj.id || '--'
      }
      return iso as string
    })
    .join(', ')
})
</script>

<template>
  <div class="rounded-lg mb-4">
    <div class="flex items-center p-5 w-120 lg:w-256">
      <Button
        v-if="isTemplateSelected"
        type="button"
        hierarchy="secondary-gray"
        size="sm"
        :icon="isExpanded ? 'chevron-down' : 'chevron-up'"
        @click="toggleExpand"
      />
      <h3 class="text-lg font-semibold text-gray-warm-900 ml-2">
        {{ t('components.desktop-list-item.desktop', { number: props.number }) }}
      </h3>
      <div class="ml-auto flex gap-2">
        <Button
          type="button"
          :hierarchy="isTemplateSelected ? 'secondary-gray' : 'primary'"
          size="sm"
          @click="openTemplateModal"
        >
          {{
            isTemplateSelected
              ? t('components.desktop-list-item.change-template')
              : t('components.desktop-list-item.select-template')
          }}
        </Button>
        <Button type="button" hierarchy="destructive" size="sm" @click="deleteDesktop">
          {{ t('components.desktop-list-item.delete-desktop') }}
        </Button>
      </div>
    </div>

    <div v-if="isExpanded && isTemplateSelected" class="p-4 pt-0">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h4 class="font-semibold text-gray-warm-800 mb-2">
            {{ t('components.desktop-list-item.preview') }}
          </h4>
          <p class="text-sm font-normal text-gray-warm-700 mb-4">
            {{ t('components.desktop-list-item.preview-description') }}
          </p>
          <div class="flex gap-4">
            <div class="relative w-24 h-24 bg-gray-warm-200 rounded shrink-0">
              <img
                v-if="localImage && localImage.url"
                :src="localImage.url"
                class="w-full h-full object-cover rounded"
                alt="Desktop preview"
              />
              <img
                v-else
                :src="mountains"
                class="w-full h-full object-cover rounded"
                alt="Default desktop preview"
              />
              <div class="absolute inset-0 flex items-center justify-center">
                <Button
                  hierarchy="secondary-gray"
                  size="sm"
                  type="button"
                  icon="image-plus"
                  @click="changeImage"
                />
              </div>
            </div>

            <div class="flex flex-col gap-4 grow">
              <div>
                <label class="block text-sm font-medium text-gray-warm-800 mb-1">
                  {{ t('components.desktop-list-item.name') }}
                </label>
                <Input
                  v-model="localName"
                  :placeholder="t('components.desktop-list-item.name-placeholder')"
                  @blur="updateName"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-warm-800 mb-1">
                  {{ t('components.desktop-list-item.description') }}
                </label>
                <Input
                  v-model="localDescription"
                  :placeholder="t('components.desktop-list-item.description-placeholder')"
                  @blur="updateDescription"
                />
              </div>
            </div>
          </div>
        </div>

        <div>
          <div class="flex items-center justify-between mb-2">
            <h4 class="font-semibold text-gray-warm-800">
              {{ t('components.desktop-list-item.hardware.title') }}
            </h4>
          </div>
          <p class="text-sm font-normal text-gray-warm-700 mb-4">
            {{ t('components.desktop-list-item.hardware.description') }}
          </p>
          <div class="bg-base-white p-4 rounded-lg border">
            <!-- System section -->
            <div class="mb-4">
              <div class="flex justify-between items-center">
                <h5 class="text-sm font-bold text-gray-warm-500 mb-2">
                  {{ t('components.desktop-list-item.hardware.system') }}
                </h5>
                <!-- <Button 
                  hierarchy="secondary-gray" 
                  size="sm" 
                  icon="settings-02"
                  @click="openHardwareModal" 
                  class="mb-1"
                /> -->
              </div>
              <div class="grid grid-cols-3 gap-2">
                <div class="flex items-center gap-2">
                  <Icon name="cpu-chip-01" />
                  <span class="text-sm">{{ localHardware.cpu }} vCPU</span>
                </div>
                <div class="flex items-center gap-2">
                  <Icon name="server-01" />
                  <span class="text-sm"
                    >{{ (localHardware.ram / 1024 / 1024).toFixed(2) }} GB RAM</span
                  >
                </div>
                <div class="flex items-center gap-2">
                  <Icon name="hard-drive" />
                  <span class="text-sm"> {{ localHardware.boot }}</span>
                </div>
              </div>
            </div>

            <div>
              <h5 class="text-sm font-bold text-gray-warm-500 mb-3">
                {{ t('components.desktop-list-item.hardware.peripherals') }}
              </h5>
              <div class="grid grid-cols-2 gap-2">
                <div class="flex items-center gap-2">
                  <Icon name="disc-02" />
                  <span class="text-sm">{{ displayIsos }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <Icon name="modem-02" />
                  <span class="text-sm">{{
                    localHardware.networkInterfaces && localHardware.networkInterfaces.length > 0
                      ? localHardware.networkInterfaces.join(', ')
                      : '--'
                  }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Template change modal -->
    <Modal
      max-width="[1100px]"
      :open="isTemplateModalOpen"
      :title="t('components.desktop-list-item.change-template-modal.title')"
      :description="t('components.desktop-list-item.change-template-modal.description')"
      @close="isTemplateModalOpen = false"
    >
      <div class="text-gray-warm-800">
        <!-- Tab navigation -->
        <div class="flex border-b border-gray-warm-200 mb-4">
          <TabsRoot v-model="localActiveTab" default-value="shared">
            <TabsList class="flex">
              <!-- Uncomment this to restore the "my" tab -->
              <!-- <TabsTrigger 
                value="my"
                class="px-4 py-2 text-sm font-medium transition-colors"
                :class="[
                  localActiveTab === 'my' 
                    ? 'border-b-2 border-brand-700 text-gray-warm-900' 
                    : 'text-gray-warm-600 hover:text-gray-warm-800'
                ]"
              >
                {{ t('components.desktop-list-item.my-templates') }}
              </TabsTrigger> -->
              <TabsTrigger
                value="shared"
                class="px-4 py-2 text-sm font-medium transition-colors"
                :class="[
                  localActiveTab === 'shared'
                    ? 'border-b-2 border-brand-700 text-gray-warm-900'
                    : 'text-gray-warm-600 hover:text-gray-warm-800'
                ]"
              >
                {{ t('components.desktop-list-item.shared-templates') }}
              </TabsTrigger>
            </TabsList>
          </TabsRoot>
        </div>

        <!-- Search input -->
        <div class="mb-4">
          <!-- TODO: search input must be in the same row as tab, right next to it. -->
          <Input
            v-model="localTemplateSearchTerm"
            type="text"
            :placeholder="t('components.desktop-list-item.search-templates')"
            icon="search-lg"
          />
        </div>

        <!-- Templates list -->
        <div class="max-h-80 overflow-y-auto flex flex-col gap-3">
          <div
            v-if="isTemplatesLoading"
            class="p-4 text-center text-gray-warm-500 justify-center items-center"
          >
            <Icon name="loading-03" size="sm" class="animate-spin" />
            {{ t('components.desktop-list-item.loading-templates') }}
          </div>
          <div v-else-if="isTemplatesError" class="p-4 text-center text-error-600">
            {{ t('components.desktop-list-item.error-loading-templates') }}
          </div>
          <div v-else-if="templates.length === 0" class="p-4 text-center text-gray-warm-500">
            {{ t('components.desktop-list-item.no-templates-found') }}
          </div>
          <TemplateListItem
            v-for="template in templates"
            v-else
            :key="template.id"
            :name="template.name"
            :description="template.description || ''"
            :image="template.image.url || ''"
            :user-name="template.user_name || ''"
            :selected="selectedTemplateId === template.id"
            :has-reservables="hasReservableVgpus(template)"
            @update:selected="() => selectTemplate(template)"
          />
        </div>
      </div>

      <template #footer>
        <div class="flex justify-end gap-2">
          <!-- <Button 
              type="button"
              hierarchy="secondary-gray" 
              @click="isTemplateModalOpen = false"
            >
            {{ t('components.desktop-list-item.cancel') }}
          </Button> -->
          <Button
            type="button"
            hierarchy="primary"
            :disabled="!selectedTemplateId"
            @click="isTemplateModalOpen = false"
          >
            {{ t('components.desktop-list-item.apply-template') }}
          </Button>
        </div>
      </template>
    </Modal>

    <Modal
      :open="isHardwareModalOpen"
      :title="t('components.desktop-list-item.edit-hardware.title')"
      :description="t('components.desktop-list-item.edit-hardware.description')"
      @close="isHardwareModalOpen = false"
    >
      <!-- Hardware edit form would go here -->
      <div class="space-y-6">
        <!-- Hardware Section -->
        <div class="border-b pb-4">
          <div class="flex items-center gap-2 font-semibold mb-4">
            <Icon name="cpu-chip-01" />
            <span class="text-sm">{{
              t('components.desktop-list-item.edit-hardware.hardware')
            }}</span>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-warm-800 mb-1">vCPU</label>
              <Input v-model="tempHardware.cpu" type="number" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-warm-800 mb-1">RAM (GB)</label>
              <Input v-model="tempHardware.ram" type="number" />
            </div>
          </div>
        </div>

        <!-- (System) Section -->
        <!-- <div class="border-b pb-4">
          <div class="flex items-center gap-2 font-semibold mb-4">
            <Icon name="monitor-01" />
            <span class="text-sm">{{ t('components.desktop-list-item.edit-hardware.system') }}</span>
          </div>
          <div class="grid grid-cols-3 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-warm-800 mb-1">Disk bus</label>
              <Input v-model="tempHardware.diskBus" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-warm-800 mb-1">Videos</label>
              <Input v-model="tempHardware.video" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-warm-800 mb-1">Boot</label>
              <Input v-model="tempHardware.boot" />
            </div>
          </div>
        </div> -->

        <!-- (Viewers) Section -->
        <div class="border-b pb-4">
          <div class="flex items-center gap-2 font-semibold mb-4">
            <Icon name="monitor-02" />
            <span class="text-sm">{{
              t('components.desktop-list-item.edit-hardware.viewers')
            }}</span>
          </div>
          <div class="mb-4">
            <label class="flex items-center gap-2 text-sm font-medium">
              <input v-model="tempHardware.fullscreen" type="checkbox" class="form-checkbox" />
              {{ t('components.desktop-list-item.edit-hardware.fullscreen') }}
            </label>
          </div>
          <div class="grid grid-cols-5 gap-2">
            <!-- TODO: Viewer option cards would go here -->
          </div>
        </div>

        <!-- (Peripherals) Section -->
        <!-- <div class="border-b pb-4">
          <div class="flex items-center gap-2 font-semibold mb-4">
            <Icon name="disc-02" />
            <span class="text-sm">{{ t('components.desktop-list-item.edit-hardware.peripherals') }}</span>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-warm-800 mb-1">ISOs</label>
              <Select v-model="tempHardware.isos" placeholder="Search ISO" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-warm-800 mb-1">Floppies</label>
              <Select placeholder="Search floppies" />
            </div>
          </div>
        </div> -->

        <!-- Bookables Section -->
        <!-- <div class="border-b pb-4">
          <div class="flex items-center gap-2 font-semibold mb-4">
            <Icon name="cpu" />
            <span class="text-sm">{{ t('components.desktop-list-item.edit-hardware.bookables') }}</span>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-warm-800 mb-1">GPU</label>
            <Select placeholder="No GPU" />
          </div>
        </div> -->

        <!-- (Network) Section -->
        <div>
          <div class="flex items-center gap-2 font-semibold mb-4">
            <Icon name="modem-02" />
            <span class="text-sm">{{
              t('components.desktop-list-item.edit-hardware.network')
            }}</span>
          </div>
          <div>
            <Button type="button" hierarchy="secondary-gray" size="sm" icon="plus">
              {{ t('components.desktop-list-item.edit-hardware.manage-networks') }}
            </Button>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="flex justify-end gap-2">
          <Button type="button" hierarchy="secondary-gray" @click="isHardwareModalOpen = false">
            {{ t('components.desktop-list-item.cancel') }}
          </Button>
          <Button type="button" hierarchy="primary" @click="saveHardwareChanges">
            {{ t('components.desktop-list-item.save-changes') }}
          </Button>
        </div>
      </template>
    </Modal>

    <ImageSelectModal
      v-model:open="showImageModal"
      :initial-selected="localImage.url"
      @select="handleImageSelected"
    />
  </div>
</template>
