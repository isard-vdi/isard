<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { Modal } from '@/components/modal'
import { Badge } from '@/components/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import { checkboxGroupItemVariants } from '@/components/checkbox-group'
import { cn } from '@/lib/utils'

import vncBrowser from '@/assets/img/viewers/vnc-browser.svg'
import rdpBrowser from '@/assets/img/viewers/rdp-browser.svg'
import spice from '@/assets/img/viewers/spice.svg'
import rdp from '@/assets/img/viewers/rdp.svg'

interface Props {
  open: boolean
  availableViewerIds: string[]
  currentViewerId: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  change: [viewerId: string]
}>()

const { t } = useI18n()

type ViewerKind = 'browser' | 'application'

interface ViewerDef {
  id: string
  image: string
  kind: ViewerKind
}

const browserViewers: ViewerDef[] = [
  { id: 'browser-vnc', image: vncBrowser, kind: 'browser' },
  { id: 'browser-rdp', image: rdpBrowser, kind: 'browser' }
]

const applicationViewers: ViewerDef[] = [
  { id: 'file-spice', image: spice, kind: 'application' },
  { id: 'file-rdpgw', image: rdp, kind: 'application' },
  { id: 'file-rdpvpn', image: rdp, kind: 'application' }
]

const selected = ref<string>(props.currentViewerId)

watch(
  () => [props.open, props.currentViewerId] as const,
  ([isOpen, current]) => {
    if (isOpen) {
      selected.value = current
    }
  }
)

const isAvailable = (id: string) => props.availableViewerIds.includes(id)

const availableBrowser = computed(() => browserViewers.filter((v) => isAvailable(v.id)))
const availableApplication = computed(() => applicationViewers.filter((v) => isAvailable(v.id)))

const modalSize = computed(() => {
  const total = availableBrowser.value.length + availableApplication.value.length
  if (total <= 2) return '2xl'
  if (total === 3) return '4xl'
  if (total === 4) return '5xl'
  return '7xl'
})

const bulletCount: Record<string, number> = {
  'browser-vnc': 3,
  'browser-rdp': 4,
  'file-spice': 3,
  'file-rdpgw': 4,
  'file-rdpvpn': 4
}

const getBulletKeys = (id: string) =>
  Array.from(
    { length: bulletCount[id] ?? 3 },
    (_, i) => `components.change-viewer-modal.bullets.${id}.${i}`
  )

const getGuideUrl = (id: string) => t(`components.change-viewer-modal.guide-url.${id}`)

const handleConfirm = () => {
  emit('change', selected.value)
  emit('close')
}
</script>

<template>
  <Modal
    :open="open"
    :size="modalSize"
    :title="t('components.change-viewer-modal.title')"
    :description="t('components.change-viewer-modal.subtitle')"
    @close="emit('close')"
  >
    <div class="flex flex-col md:flex-row md:justify-center md:items-stretch gap-4 py-4">
      <div v-if="availableBrowser.length > 0" class="flex flex-wrap justify-center gap-3">
        <div
          v-for="viewer in availableBrowser"
          :key="viewer.id"
          :class="
            cn(
              checkboxGroupItemVariants({ kind: 'image', selected: selected === viewer.id }),
              'relative w-56 pt-6 pb-4 px-4 gap-3 rounded-xl'
            )
          "
          role="radio"
          :aria-checked="selected === viewer.id"
          tabindex="0"
          @click="selected = viewer.id"
          @keydown.enter.prevent="selected = viewer.id"
          @keydown.space.prevent="selected = viewer.id"
        >
          <Badge
            color="viewer-blue"
            shape="square"
            size="sm"
            :content="t('components.change-viewer-modal.badge.browser')"
            class="absolute -top-2 left-4"
          />
          <div class="absolute top-2 right-2">
            <Checkbox
              :model-value="selected === viewer.id"
              type="radio"
              size="sm"
              class="bg-base-white pointer-events-none"
            />
          </div>
          <div class="flex flex-col items-center gap-2">
            <img :src="viewer.image" :alt="t(`viewers.${viewer.id}`)" class="h-16 w-auto" />
            <p class="text-md font-semibold text-gray-warm-900">
              {{ t(`viewers.${viewer.id}`) }}
            </p>
          </div>
          <ul class="flex-1 flex flex-col gap-1 list-disc pl-5 text-xs text-gray-warm-600">
            <li v-for="key in getBulletKeys(viewer.id)" :key="key">
              {{ t(key) }}
            </li>
          </ul>
          <Button
            as="a"
            hierarchy="secondary-gray"
            :href="getGuideUrl(viewer.id)"
            target="_blank"
            rel="noopener noreferrer"
            class="mt-auto self-center"
            @click.stop
          >
            {{ t('components.change-viewer-modal.show-guide') }}
          </Button>
        </div>
      </div>

      <Separator
        v-if="availableBrowser.length > 0 && availableApplication.length > 0"
        orientation="vertical"
        class="hidden md:flex h-56 mx-2 self-center shrink-0"
      />

      <div v-if="availableApplication.length > 0" class="flex flex-wrap justify-center gap-3">
        <div
          v-for="viewer in availableApplication"
          :key="viewer.id"
          :class="
            cn(
              checkboxGroupItemVariants({ kind: 'image', selected: selected === viewer.id }),
              'relative w-56 pt-6 pb-4 px-4 gap-3 rounded-xl'
            )
          "
          role="radio"
          :aria-checked="selected === viewer.id"
          tabindex="0"
          @click="selected = viewer.id"
          @keydown.enter.prevent="selected = viewer.id"
          @keydown.space.prevent="selected = viewer.id"
        >
          <Badge
            color="viewer-violet"
            shape="square"
            size="sm"
            :content="t('components.change-viewer-modal.badge.application')"
            class="absolute -top-2 left-4"
          />
          <div class="absolute top-2 right-2">
            <Checkbox
              :model-value="selected === viewer.id"
              type="radio"
              size="sm"
              class="bg-base-white pointer-events-none"
            />
          </div>
          <div class="flex flex-col items-center gap-2">
            <img :src="viewer.image" :alt="t(`viewers.${viewer.id}`)" class="h-16 w-auto" />
            <p class="text-md font-semibold text-gray-warm-900">
              {{ t(`viewers.${viewer.id}`) }}
            </p>
          </div>
          <ul class="flex-1 flex flex-col gap-1 list-disc pl-5 text-xs text-gray-warm-600">
            <li v-for="key in getBulletKeys(viewer.id)" :key="key">
              {{ t(key) }}
            </li>
          </ul>
          <Button
            as="a"
            hierarchy="secondary-gray"
            :href="getGuideUrl(viewer.id)"
            target="_blank"
            rel="noopener noreferrer"
            class="mt-auto self-center"
            @click.stop
          >
            {{ t('components.change-viewer-modal.show-guide') }}
          </Button>
        </div>
      </div>
    </div>

    <template #footer>
      <Button hierarchy="secondary-gray" size="lg" @click="emit('close')">
        {{ t('components.change-viewer-modal.cancel') }}
      </Button>
      <Button hierarchy="primary" size="lg" @click="handleConfirm">
        {{ t('components.change-viewer-modal.confirm') }}
      </Button>
    </template>
  </Modal>
</template>
