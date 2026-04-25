<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import Modal from '@/components/modal/Modal.vue'
import { Button } from '@/components/ui/button'
import { DraggableItem } from '@/components/drag-and-drop'
import { Icon } from '@/components/icon'
import { useI18n } from 'vue-i18n'
import { monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter'
import { extractClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge'
import { reorderWithEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/util/reorder-with-edge'
import { triggerPostMoveFlash } from '@atlaskit/pragmatic-drag-and-drop-flourish/trigger-post-move-flash'
import { onMounted, onUnmounted } from 'vue'

interface Network {
  id: string
  name: string
}

interface Props {
  open: boolean
  selectedNetworks: ({ id: string } | string)[]
  availableNetworks: Network[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  save: [selectedNetworks: string[]]
}>()

const { t } = useI18n()

// Normalize selected networks to IDs
const normalizeToId = (item: { id: string } | string): string => {
  return typeof item === 'string' ? item : item.id
}

// Local state for manipulation
const selected = ref<string[]>([])
const available = computed(() =>
  props.availableNetworks.filter((n) => !selected.value.includes(n.id))
)

// Initialize local state when modal opens
watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      selected.value = props.selectedNetworks.map(normalizeToId)
    }
  },
  { immediate: true }
)

// Get network info by ID from available networks
const getNetworkInfo = (id: string): Network | undefined => {
  return props.availableNetworks.find((n) => n.id === id)
}

const addNetwork = (networkId: string, index?: number) => {
  if (!selected.value.includes(networkId)) {
    if (index !== undefined) {
      selected.value.splice(index, 0, networkId)
    } else {
      selected.value.push(networkId)
    }
  }
}

// Remove network from selected
const removeNetwork = (networkId: string) => {
  selected.value = selected.value.filter((id) => id !== networkId)
}

// Save and close
const handleSave = () => {
  emit('save', selected.value)
  emit('close')
}

const handleClose = () => {
  emit('close')
}

// Drop zones for cross-list drag
const selectedDropZoneRef = ref<HTMLElement | null>(null)
const isDropZoneActive = ref(false)

let cleanup: () => void = () => {
  /* noop — replaced on mount */
}
onMounted(() => {
  // Use monitor to detect drops from available to selected
  cleanup = monitorForElements({
    onDrop: ({ location, source }) => {
      const target = location.current.dropTargets[0]
      if (!target) {
        return
      }

      const sourceData = source.data
      const targetData = target.data

      console.debug('Drop detected from source to target:', sourceData, targetData)

      if (sourceData.item.index < 0 || targetData.item.index < 0) {
        return
      }

      const closestEdgeOfTarget = extractClosestEdge(targetData)

      if (closestEdgeOfTarget === 'bottom') {
        addNetwork(sourceData.item.value, targetData.item.index)
      } else {
        addNetwork(sourceData.item.value, targetData.item.index + 1)
      }

      // Using `flushSync` so we can query the DOM straight after this line
      selected.value = reorderWithEdge({
        list: selected.value,
        startIndex: sourceData.index,
        indexOfTarget: targetData.index,
        closestEdgeOfTarget,
        axis: 'vertical'
      })

      // Being simple and just querying for the task after the drop.
      // We could use react context to register the element in a lookup,
      // and then we could retrieve that element after the drop and use
      // `triggerPostMoveFlash`. But this gets the job done.
      const element = document.querySelector(`[data-item-id="${sourceData.item.value}"]`)
      if (element instanceof HTMLElement) {
        triggerPostMoveFlash(element)
      }

      // addNetwork(sourceData.item.value, targetData.item.index);
      isDropZoneActive.value = false
    },
    onDrag: ({ location, source }) => {
      const item = source.data.item as { value: string; label: string }
      if (!item || !item.value) return

      const dropTargets = location.current.dropTargets

      // Check if hovering over the selected zone
      const isOverZone = dropTargets.some((target) =>
        selectedDropZoneRef.value?.contains(target.element)
      )

      // Highlight if hovering over selected zone and not already selected
      if (isOverZone && !selected.value.includes(item.value)) {
        isDropZoneActive.value = true
      } else {
        isDropZoneActive.value = false
      }
    }
  })

  onUnmounted(cleanup)
})
</script>

<template>
  <Modal
    :open="props.open"
    :title="t('components.domain.hardware.networks.modal.title')"
    :description="t('components.domain.hardware.networks.modal.description')"
    size="4xl"
    @close="handleClose"
  >
    <div class="flex gap-6 min-h-[400px]">
      <!-- Selected Networks Column -->
      <div class="flex-1 flex flex-col">
        <h3 class="text-sm font-semibold text-gray-warm-900 mb-3">
          {{ t('components.domain.hardware.networks.modal.selected') }}
        </h3>
        <div
          ref="selectedDropZoneRef"
          targetId="testing"
          class="flex-1 border border-gray-warm-200 rounded-lg p-3 space-y-2 overflow-y-auto min-h-[300px]"
          :class="{
            'bg-brand-50': selected.length === 0,
            'bg-brand-100 scale-[1.01]': isDropZoneActive
          }"
        >
          <DraggableItem
            v-for="(networkId, index) in selected"
            :key="networkId"
            :item="{
              value: networkId,
              label: getNetworkInfo(networkId)?.name || networkId
            }"
            :index="index"
          >
            <template #default="{ item }">
              <div class="flex items-center justify-between w-full">
                <div class="flex items-center gap-2">
                  <!-- Add the item position indicator -->
                  <span class="text-sm text-gray-warm-500">{{ index + 1 }}</span>
                  <span class="text-sm text-gray-warm-900">{{ item.label }}</span>
                </div>
                <Button hierarchy="link-color" size="sm" @click.stop="removeNetwork(networkId)">
                  <Icon name="x-close" size="sm" stroke-color="error-500" />
                </Button>
              </div>
            </template>
          </DraggableItem>
          <div
            v-if="isDropZoneActive"
            class="flex items-center justify-center h-full text-gray-warm-400 text-sm"
          >
            {{ t('components.domain.hardware.networks.modal.drop-here') }}
          </div>
          <div
            v-if="selected.length === 0"
            class="flex items-center justify-center h-full text-gray-warm-400 text-sm"
          >
            {{ t('components.domain.hardware.networks.modal.empty-selected') }}
          </div>
        </div>
      </div>

      <!-- Available Networks Column -->
      <div class="flex-1 flex flex-col">
        <h3 class="text-sm font-semibold text-gray-warm-900 mb-3">
          {{ t('components.domain.hardware.networks.modal.available') }}
        </h3>
        <div
          class="flex-1 border-2 border-dashed border-gray-warm-200 rounded-lg p-3 space-y-2 overflow-y-auto min-h-[300px] transition-all"
        >
          <DraggableItem
            v-for="(network, index) in available"
            :key="network.id"
            :item="{ value: network.id, label: network.name }"
            :index="index"
            :can-reorder="false"
          >
            <template #default="{ item }">
              <div class="flex items-center justify-between w-full">
                <div class="flex items-center gap-2">
                  <span class="text-sm text-gray-warm-900">{{ item.label }}</span>
                </div>
                <Button hierarchy="link-color" size="sm" @click.stop="addNetwork(network.id)">
                  <Icon name="plus" size="sm" stroke-color="brand-500" />
                </Button>
              </div>
            </template>
          </DraggableItem>
          <div
            v-if="available.length === 0"
            class="flex items-center justify-center h-full text-gray-warm-400 text-sm"
          >
            {{ t('components.domain.hardware.networks.modal.empty-available') }}
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-3 px-6 pb-6">
        <Button hierarchy="link-gray" @click="handleClose">
          {{ t('components.domain.hardware.networks.modal.cancel') }}
        </Button>
        <Button hierarchy="primary" @click="handleSave">
          {{ t('components.domain.hardware.networks.modal.save') }}
        </Button>
      </div>
    </template>
  </Modal>
</template>
