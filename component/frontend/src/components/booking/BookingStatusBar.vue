<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import type { BookingPriorityState } from '@/stores/booking'

interface Props {
  priority: BookingPriorityState
  showAddBooking?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showAddBooking: true
})

const emit = defineEmits<{
  addBooking: []
}>()

const { t } = useI18n()
</script>

<template>
  <div id="statusbar" class="flex items-center flex-wrap gap-4 py-2">
    <div class="flex items-center gap-4 text-gray-warm-500 text-sm">
      <span>
        <span class="hidden lg:inline"
          >{{ t('components.bookings.item.status-bar.forbid-time') }}:</span
        >
        {{ ` ${props.priority.forbidTime} min` }}
      </span>
      <span>
        <span class="hidden lg:inline"
          >{{ t('components.bookings.item.status-bar.max-time') }}:</span
        >
        {{ ` ${props.priority.maxTime} min` }}
      </span>
      <span>
        <span class="hidden lg:inline"
          >{{ t('components.bookings.item.status-bar.max-items') }}:</span
        >
        {{ ` ${props.priority.maxItems}` }}
      </span>
    </div>
    <div v-if="props.showAddBooking" class="ml-auto">
      <Button hierarchy="secondary-color" size="sm" @click="emit('addBooking')">
        {{ t('components.bookings.item.status-bar.buttons.add-booking') }}
      </Button>
    </div>
  </div>
</template>
