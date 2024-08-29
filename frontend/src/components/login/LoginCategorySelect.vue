<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { type CategorySelectToken } from '.'
import {
  getToken as getAuthToken,
  isCategorySelectClaims,
  removeToken as removeAuthToken,
  useCookies as useAuthCookies
} from '@/lib/auth'
import { Button } from '@/components/ui/button'

const { t } = useI18n()
const cookies = useAuthCookies()

interface Props {
  categories: CategorySelectToken
}

const name = computed(() => {
  const token = getAuthToken(cookies)
  if (!token) {
    return undefined
  }

  if (!isCategorySelectClaims(token)) {
    return undefined
  }

  return token.user.name
})

const logout = () => {
  removeAuthToken(cookies)
}

const onClick = (categoryId: string) => {
  emit('submit', categoryId)
}

const props = defineProps<Props>()

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
  <div class="mt-[48px] flex flex-col justify-center items-center text-center">
    <p>
      {{ t('components.login.login-category-select.logged-in-as') }} <b>{{ name }}</b>
    </p>
    <Button class="mt-[8px]" hierarchy="link-color" @click="logout">{{
      t('components.login.login-category-select.logout')
    }}</Button>
  </div>
</template>
