<script setup lang="ts">
import { computed } from 'vue'
import CardTag from './CardTab.vue'
import CardHeader from './CardHeader.vue'
import CardContent from './CardContent.vue'
import CardTitle from './CardTitle.vue'
import CardDescription from './CardDescription.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  kind: 'persistent' | 'volatile' | 'deployment' | 'lab'
  title: string
  description: string
  backgroundImage?: string
  desktopsCount?: number
  status?: string
  shutdownTime?: string
  viewers?: string[]
  preferredViewer?: string
  needsBooking?: boolean
  buttons?: object[]
}>()

const warningText = computed(() => {
  if (props.shutdownTime && Number(props.shutdownTime) > 0) {
    return t('components.card.card-header.auto-shutdown', { time: props.shutdownTime })
  }
  return undefined
})

const options = computed(() => {
  if (props.kind === 'lab') {
    return ['info']
  }
  return ['network', 'menu']
})
</script>

<template>
  <div class="card rounded-lg overflow-hidden shadow-md relative">
    <!-- Tag -->
    <CardTag :kind="props.kind" class="absolute top-0 left-0 z-0" />
    <div
      v-if="warningText"
      class="absolute bottom-[140px] left-[47px] flex items-center gap-2 px-3 py-1.5 rounded-md text-sm text-white bg-[#13131366] backdrop-blur-xs backdrop-blur-xs"
    >
      <Icon name="alert-circle" class="w-4 h-4 text-warning-600" />
      <span class="text-xs font-medium leading-tight">
        {{ warningText }}
      </span>
    </div>
    <!-- Header -->
    <CardHeader
      :background-image="backgroundImage"
      :title="title || ''"
      :description="description || ''"
      :desktops-count="desktopsCount || 0"
      :card-menus="options"
    >
      <CardContent>
        <CardTitle :title="title || ''" />
        <CardDescription :description="description || ''" />
      </CardContent>
    </CardHeader>

    <!-- Footer -->
    <CardFooter>
      <slot name="footer" />
    </CardFooter>
  </div>
</template>

<style scoped>
.card {
  background-color: white;
  width: 426px;
  height: 310px;
  display: flex;
  flex-direction: column;
}
</style>
