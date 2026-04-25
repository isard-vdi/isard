<script setup lang="ts">
import { Skeleton } from '@/components/ui/skeleton'
import browserIcon from '@/assets/img/viewers/vnc-browser.svg?component'
</script>

<template>
  <div class="bg-white rounded-[15px] py-4 px-4 text-center w-full max-w-md m-2">
    <component :is="browserIcon" class="w-full h-20 mx-auto mb-3" />
    <Skeleton class="h-9 w-full mt-3" />
  </div>
</template>
