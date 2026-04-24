<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from '@/components/ui/button/Button.vue'
import Avatar from '@/components/ui/avatar/Avatar.vue'

import mountains from '@/assets/img/mountains.svg'
import { useI18n } from 'vue-i18n'

interface Props {
  image?: string
  name: string
  description: string
  userAvatar?: string
  userName: string
  selected: boolean
  hasReservables?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  image: () => mountains,
  userAvatar: undefined,
  selected: false,
  hasReservables: false
})

const emit = defineEmits(['update:selected'])

const { t } = useI18n()

// Temporary fix: prevent selection if template has reservables.vgpus until deployments can be booked
const canSelect = computed(() => !props.hasReservables)
</script>

<template>
  <div
    class="w-full flex h-16 items-center bg-base-white border border-gray-warm-200 rounded-2xl hover:bg-gray-warm-300 cursor-pointer"
    :class="{
      'bg-gray-warm-200 ring-2 ring-gray-warm-100': props.selected,
      'opacity-50 cursor-not-allowed border-error-500 hover:bg-base-white': props.hasReservables
    }"
    @click="canSelect ? emit('update:selected', !props.selected) : null"
  >
    <!-- Template image -->
    <div class="w-48 h-full overflow-hidden shrink-0">
      <img
        :src="props.image"
        alt="Template preview"
        class="rounded-l-2xl h-full w-full object-cover"
      />
    </div>

    <!-- Template name -->
    <div class="px-3 flex items-center min-w-0 w-48 shrink-0">
      <p class="text-sm font-semibold text-gray-warm-900 truncate">{{ props.name }}</p>
    </div>

    <!-- Template description -->
    <div class="px-3 pr-4 grow min-w-0">
      <p v-if="!props.hasReservables" class="text-xs font-medium text-gray-warm-600 line-clamp-2">
        {{ props.description }}
      </p>
      <p v-else class="text-xs font-medium text-error-500 line-clamp-2">
        {{ t('components.desktop-list-item.template-has-reservables') }}
      </p>
    </div>

    <!-- User information -->
    <div class="px-3 flex items-center shrink-0 w-48">
      <Avatar size="xs" :label="props.userName">
        <img v-if="props.userAvatar" :src="props.userAvatar" alt="User avatar" />
        <div
          v-else
          class="w-full h-full bg-gray-warm-200 flex items-center justify-center text-gray-warm-600 text-xs font-medium"
        >
          {{ props.userName.charAt(0).toUpperCase() }}
        </div>
      </Avatar>
    </div>

    <!-- Info button -->
    <!-- <div class="px-3 shrink-0">
            <Button 
                size="sm" 
                hierarchy="secondary-gray" 
                icon="info-circle"
                :icon-stroke-color="'var(--gray-warm-700)'"
            />
        </div> -->
  </div>
</template>
