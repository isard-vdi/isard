<script setup lang="ts">
import { computed, ref } from 'vue'
import { useVModel } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { type GetCategoriesResponse } from '@/gen/oas/api'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem
} from '@/components/ui/select'

const { t } = useI18n()

interface Props {
  categories: GetCategoriesResponse
  modelValue?: string
}

const props = defineProps<Props>()
const emits = defineEmits<{
  (e: 'update:modelValue', payload: string): void
}>()

const categoriesToShow = computed(() => props.categories.filter((category) => category.frontend))

const modelValue = useVModel(props, 'modelValue', emits, {
  passive: true
})

const open = ref(false)
const focused = ref(false)
const hierarchy = computed(() => (focused.value && modelValue.value === '' ? 'destructive' : null))
const focus = () => {
  focused.value = true
  open.value = true
}

defineExpose({
  focus
})
</script>

<template>
  <Select v-model:modelValue="modelValue" v-model:open="open">
    <SelectTrigger :hierarchy="hierarchy">
      <SelectValue :placeholder="t('components.login.login-categories-dropdown.placeholder')" />
    </SelectTrigger>
    <SelectContent>
      <SelectGroup>
        <SelectItem v-for="cat in categoriesToShow" :key="cat.id" :value="cat.id">{{
          cat.name
        }}</SelectItem>
      </SelectGroup>
    </SelectContent>
  </Select>
</template>
