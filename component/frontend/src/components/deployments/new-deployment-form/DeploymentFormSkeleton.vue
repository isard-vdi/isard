<script setup lang="ts">
import { DesktopCardSkeleton } from '@/components/desktop-card'
import { Skeleton } from '@/components/ui/skeleton'
</script>

<template>
  <div class="grid grid-cols-2 gap-12 w-full">
    <div class="flex flex-col gap-4 w-full">
      <Skeleton class="h-6 w-1/3" />
      <Skeleton class="h-4 w-3/4" />

      <DesktopCardSkeleton class="w-[426px] h-[310px]" />
    </div>

    <div class="flex flex-col gap-4 w-full">
      <Skeleton class="h-6 w-1/3" />
      <Skeleton class="h-4 w-3/4" />

      <Skeleton class="h-10 mt-8" />
      <Skeleton class="h-32 mt-8" />
    </div>

    <div
      v-for="i in 3"
      :key="i"
      class="flex flex-col gap-4 w-full"
      :class="{
        'col-span-full': i === 3
      }"
    >
      <Skeleton class="h-6 w-1/3" />
      <Skeleton class="h-4 w-3/4" />

      <Skeleton class="h-10 w-1/2 mt-4" />
    </div>
  </div>
</template>
