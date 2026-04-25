<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/icon'

interface Props {
  open?: boolean
  documentationUrl?: string
}

const props = withDefaults(defineProps<Props>(), { open: false, documentationUrl: '' })
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()

function detectOs(): string | null {
  const userAgent = window.navigator.userAgent
  const platform = window.navigator.platform
  const macosPlatforms = ['Macintosh', 'MacIntel', 'MacPPC', 'Mac68K', 'Mac OS']
  const windowsPlatforms = ['Win32', 'Win64', 'Windows', 'WinCE']
  const iosPlatforms = ['iPhone', 'iPad', 'iPod']
  if (macosPlatforms.indexOf(platform) !== -1) return 'MacOS'
  if (iosPlatforms.indexOf(platform) !== -1) return 'iOS'
  if (windowsPlatforms.indexOf(platform) !== -1) return 'Windows'
  if (/Android/.test(userAgent)) return 'Android'
  if (/Linux/.test(platform)) return 'Linux'
  return null
}

const os = detectOs()
</script>

<template>
  <Dialog :open="props.open" @update:open="(v) => !v && emit('close')">
    <DialogContent
      class="bg-base-background shadow-md max-h-[90vh] flex flex-col p-0 w-[95vw] max-w-2xl"
    >
      <DialogHeader class="px-6 pt-6">
        <DialogTitle class="flex items-center gap-2 text-gray-warm-900 text-lg">
          <Icon name="star-01" stroke-color="warning-500" size="md" />
          {{ t('views.direct-viewer.help.spice.local-client') }}
        </DialogTitle>
        <DialogDescription class="sr-only">
          {{ t('views.direct-viewer.help.spice.spice-help') }}
        </DialogDescription>
      </DialogHeader>

      <div class="px-6 pb-2 overflow-y-auto text-sm text-gray-warm-700">
        <hr class="my-3 border-gray-warm-300" />
        <p>
          <strong>{{ t('views.direct-viewer.help.spice.best-performance') }}</strong>
          {{ t('views.direct-viewer.help.spice.spice-client-required') }}
        </p>
        <p class="mt-2">{{ t('views.direct-viewer.help.spice.generic-text') }}</p>

        <div class="flex justify-center my-4">
          <Button
            v-if="props.documentationUrl"
            as="a"
            hierarchy="secondary-color"
            :href="props.documentationUrl"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ t('views.direct-viewer.help.spice.download-install') }}
          </Button>
        </div>

        <p v-if="os !== 'MacOS'" class="mt-2 mb-4">
          {{ t('views.direct-viewer.help.spice.once-installed') }}
        </p>
      </div>

      <DialogFooter class="px-6 pb-4 sm:justify-center">
        <Button hierarchy="primary" @click="emit('close')">
          {{ t('views.direct-viewer.help.spice.close-guide') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
