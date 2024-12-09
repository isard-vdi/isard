<script setup lang="ts">
import { defineProps, defineEmits } from 'vue'
import { useI18n } from 'vue-i18n'
import CardBox from '@/components/card-box/CardBox.vue'
import Icon from '@/components/icon/Icon.vue'

const { t } = useI18n()

interface Props {
  title: string
  count: number
  colorClass: string
  icon?: string
  warning?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits(['click'])
</script>

<template>
  <div>
    <CardBox :icon="props.icon" @click="emit('click')">
      <span
        v-if="props.warning"
        class="absolute top-2 left-2 w-10 h-10 rounded-md flex items-center justify-center bg-error-400"
        :title="t('components.migration.migration-item-box.quota_exceeded', { type: props.title })"
      >
        <Icon name="alert-triangle" />
      </span>

      <p class="text-lg font-semibold text-gray-900">{{ props.title }}</p>
      <p :class="['text-2xl font-bold', props.colorClass]">{{ props.count }}</p>
    </CardBox>
  </div>
</template>
