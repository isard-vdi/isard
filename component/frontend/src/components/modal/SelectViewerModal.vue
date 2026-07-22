<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Modal from '@/components/modal/Modal.vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'

import vncBrowser from '@/assets/img/viewers/vnc-browser.svg?component'
import rdpBrowser from '@/assets/img/viewers/rdp-browser.svg?component'
import spice from '@/assets/img/viewers/spice.svg?component'
import rdp from '@/assets/img/viewers/rdp.svg?component'

const { t } = useI18n()

export interface Props {
  open?: boolean
  selectedViewers: string[]
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<{
  close: []
  confirm: [viewers: string[]]
}>()

const selected = ref<string[]>([...props.selectedViewers])

const viewers = [
  { id: 'vnc', name: t('components.viewers-modal.vnc-browser'), icon: vncBrowser },
  { id: 'rdp-browser', name: t('components.viewers-modal.rdp-browser'), icon: rdpBrowser },
  { id: 'spice', name: t('components.viewers-modal.spice'), icon: spice },
  { id: 'rdp', name: t('components.viewers-modal.rdp'), icon: rdp },
  { id: 'rdp-vpn', name: t('components.viewers-modal.rdp-vpn'), icon: rdp }
]

const toggleViewer = (id: string) => {
  const index = selected.value.indexOf(id)
  if (index > -1) {
    selected.value.splice(index, 1)
  } else {
    selected.value.push(id)
  }
}

const handleConfirm = () => {
  emit('confirm', selected.value)
  emit('close')
}

const handleSubmit = (e: Event) => {
  e.preventDefault()
  handleConfirm()
}
</script>

<template>
  <Modal
    :title="t('components.viewers-modal.title')"
    :description="t('components.viewers-modal.description')"
    :open="open"
    max-width="256"
    class="p-6 px-2 w-200"
    @close="emit('close')"
  >
    <form @submit="handleSubmit">
      <div class="grid grid-cols-5 pb-5">
        <button
          v-for="viewer in viewers"
          :key="viewer.id"
          type="button"
          class="relative p-3 bg-white rounded-lg border flex flex-col items-center hover:border-brand-600 w-32"
          :class="
            selected.includes(viewer.id) ? 'border-brand-600 border-2' : 'border-gray-warm-300'
          "
          @click="toggleViewer(viewer.id)"
        >
          <component :is="viewer.icon" class="w-24 h-14" />
          <span class="text-xs font-semibold text-gray-warm-700">{{ viewer.name }}</span>

          <Checkbox
            :key="`checkbox-${viewer.id}-${selected.includes(viewer.id)}`"
            :checked="selected.includes(viewer.id)"
            :model-value="selected.includes(viewer.id)"
            class="absolute top-2 right-2 pointer-events-none"
            @click.stop
          />
        </button>
      </div>

      <div class="flex justify-center items-center gap-3 w-full px-6 pt-3">
        <Button type="button" hierarchy="link-gray" size="lg" class="w-48" @click="emit('close')">
          {{ t('components.viewers-modal.cancel') }}
        </Button>
        <Button type="submit" hierarchy="primary" size="lg" class="flex-1">
          {{ t('components.viewers-modal.accept') }}
        </Button>
      </div>
    </form>
  </Modal>
</template>
