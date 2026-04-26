<script setup lang="ts">
import { Maximize2 } from 'lucide-vue-next'

import NoVNC from '@/components/noVNC/NoVNC.vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

import type { VideowallDesktop } from './types'

defineProps<{ desktop: VideowallDesktop }>()
defineEmits<{ select: [] }>()
</script>

<template>
  <div
    class="rounded-lg border bg-card shadow-sm overflow-hidden cursor-pointer hover:shadow-md transition-shadow"
    @click="$emit('select')"
  >
    <div class="flex items-center gap-2 p-3 border-b">
      <Avatar size="sm">
        <AvatarImage :src="desktop.userPhoto ?? ''" referrerpolicy="no-referrer" />
        <AvatarFallback>
          {{ (desktop.userName ?? '').slice(0, 2).toUpperCase() }}
        </AvatarFallback>
      </Avatar>
      <span class="text-sm text-muted-foreground truncate flex-1">
        {{ desktop.userName }}
      </span>
      <Maximize2 class="h-4 w-4 shrink-0" />
    </div>

    <NoVNC
      v-if="desktop.viewer"
      :viewer="desktop.viewer.values"
      height="200px"
      view-only
      :quality-level="0"
      :compression-level="9"
      background="transparent"
    />
    <div
      v-else
      class="flex flex-col items-center justify-center bg-base-black"
      style="height: 200px"
    >
      <div
        class="rounded-full"
        style="
          width: 70px;
          height: 70px;
          opacity: 0.5;
          background: #d5d5cd url(/api/v4/logo) center / 70px 70px no-repeat;
        "
      />
      <p class="text-base-white text-center mt-2">
        {{ $t('views.deployment-videowall.desktop-not-available') }}
      </p>
    </div>
  </div>
</template>
