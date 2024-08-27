<script setup lang="ts">
import { type CategorySelectToken } from '.'
import { Button } from '@/components/ui/button'

interface Props {
  categories: CategorySelectToken
}
const props = defineProps<Props>()

const onClick = (categoryId: string) => {
  emit('submit', categoryId)
}

const emit = defineEmits<{
  submit: [categoryId: string]
}>()
</script>

<template>
  <div :class="props.categories.length > 5 ? 'grid-cols-2' : 'grid-cols-1'" class="grid gap-4">
    <template v-for="category in props.categories" :key="category.name">
      <Button class="w-100" hierarchy="secondary-gray" @click="onClick(category.id)">{{
        category.name
      }}</Button>
    </template>
  </div>
</template>
