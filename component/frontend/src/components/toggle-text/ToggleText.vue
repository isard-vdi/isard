<script setup lang="ts">
import { ToggleGroup, ToggleGroupItem } from '../ui/toggle-group'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Props {
  left: PropsOptions
  right: PropsOptions
}

interface PropsOptions {
  value: string
  label: string
}

const props = defineProps<Props>()
const selected = ref<string>(props.left.value)

function changeSelection(selectedValue: string) {
  if (selected.value !== selectedValue) {
    selected.value = selectedValue
  }
}
</script>

<template>
  <ToggleGroup v-model="selected" type="single" size="default">
    <ToggleGroupItem
      :value="props.left.value"
      size="default"
      variant="right"
      :class="selected === props.left.value"
      @click="changeSelection(props.left.value)"
    >
      {{ t(props.left.label) }}
    </ToggleGroupItem>
    <ToggleGroupItem
      :value="props.right.value"
      size="default"
      variant="left"
      :class="selected === props.right.value"
      @click="changeSelection(props.right.value)"
    >
      {{ t(props.right.label) }}
    </ToggleGroupItem>
  </ToggleGroup>
</template>
