<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'
import { useI18n } from 'vue-i18n'

import { desktopStatusBadgeColor, desktopStatusLabel } from '@/lib/desktops'
import { cn } from '@/lib/utils'

import { Badge } from '@/components/badge'

interface Props {
  status?: string | null
  class?: HTMLAttributes['class']
}

const { status, class: className } = defineProps<Props>()

const i18n = useI18n()

const color = computed(() => desktopStatusBadgeColor(status ?? undefined))
const label = computed(() => desktopStatusLabel(status ?? undefined, i18n))
</script>

<template>
  <Badge
    :color="color"
    :content="label"
    shape="square"
    size="sm"
    :class="cn('font-bold shrink-0', className)"
  />
</template>
