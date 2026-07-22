<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

import { DataTableRow, DataTableCell } from '.'

interface Props {
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <DataTableRow>
    <DataTableCell :class="cn('col-span-full p-2', props.class)">
      <div class="w-full flex items-center justify-center min-h-24">
        <slot />
      </div>
    </DataTableCell>
  </DataTableRow>
</template>
