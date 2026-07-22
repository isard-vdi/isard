<script setup lang="ts">
import { computed } from 'vue'
import { CheckboxGroupImageItem, type ImageItem } from '@/components/checkbox-group/image-item'
import { Separator } from '@/components/ui/separator'
import { useI18n } from 'vue-i18n'
import rdpBrowser from '@/assets/img/viewers/rdp-browser.svg'
import rdp from '@/assets/img/viewers/rdp.svg'
import spice from '@/assets/img/viewers/spice.svg'
import vncBrowser from '@/assets/img/viewers/vnc-browser.svg'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Icon } from '@/components/icon'

interface Props {
  modelValue: string[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [viewers: string[]]
}>()

const { t } = useI18n()

const browserViewers: ImageItem[] = [
  {
    image: rdpBrowser,
    label: t('components.viewers-selector.browser-viewers.rdp-browser'),
    value: 'browser_rdp'
  },
  {
    image: vncBrowser,
    label: t('components.viewers-selector.browser-viewers.vnc-browser'),
    value: 'browser_vnc'
  }
]

const fileViewers: ImageItem[] = [
  { image: rdp, label: t('components.viewers-selector.file-viewers.rdp'), value: 'file_rdpgw' },
  { image: spice, label: t('components.viewers-selector.file-viewers.spice'), value: 'file_spice' },
  { image: rdp, label: t('components.viewers-selector.file-viewers.rdp-vpn'), value: 'file_rdpvpn' }
]

const toggleViewer = (viewerValue: string) => {
  const currentViewers = props.modelValue || []
  const index = currentViewers.indexOf(viewerValue)

  if (index > -1) {
    emit(
      'update:modelValue',
      currentViewers.filter((v) => v !== viewerValue)
    )
  } else {
    emit('update:modelValue', [...currentViewers, viewerValue])
  }
}

const isViewerSelected = (viewerValue: string) => {
  return props.modelValue?.includes(viewerValue) || false
}
</script>

<template>
  <div class="flex items-start gap-4">
    <div class="flex flex-col gap-2">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger as-child>
            <h3 class="text-sm font-medium text-gray-warm-700">
              {{ t('components.viewers-selector.browser-viewers.label') }}
              <Icon name="info-circle" size="xs" class="inline-block" />
            </h3>
          </TooltipTrigger>
          <TooltipContent
            :title="t('components.viewers-selector.browser-viewers.label')"
            :subtitle="t('components.viewers-selector.browser-viewers.info')"
          />
        </Tooltip>
      </TooltipProvider>
      <div class="flex flex-wrap gap-3">
        <div
          v-for="viewer in browserViewers"
          :key="viewer.value"
          :class="!isViewerSelected(viewer.value) ? 'unselected-viewer' : ''"
        >
          <CheckboxGroupImageItem
            :item="viewer"
            :is-selected="isViewerSelected(viewer.value)"
            @check="toggleViewer(viewer.value)"
          />
        </div>
      </div>
    </div>
    <Separator orientation="vertical" class="h-[150px]" />
    <div class="flex flex-col gap-2">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger as-child>
            <h3 class="text-sm font-medium text-gray-warm-700">
              {{ t('components.viewers-selector.file-viewers.label') }}
              <Icon name="info-circle" size="xs" class="inline-block" />
            </h3>
          </TooltipTrigger>
          <TooltipContent
            :title="t('components.viewers-selector.file-viewers.label')"
            :subtitle="t('components.viewers-selector.file-viewers.info')"
          />
        </Tooltip>
      </TooltipProvider>
      <div class="flex flex-wrap gap-3">
        <div
          v-for="viewer in fileViewers"
          :key="viewer.value"
          :class="!isViewerSelected(viewer.value) ? 'unselected-viewer' : ''"
        >
          <CheckboxGroupImageItem
            :item="viewer"
            :is-selected="isViewerSelected(viewer.value)"
            @check="toggleViewer(viewer.value)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.unselected-viewer :deep(img) {
  filter: contrast(0.5);
}
</style>
