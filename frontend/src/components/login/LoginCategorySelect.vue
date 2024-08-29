<script setup lang="ts">
import { type CategorySelectToken } from '.'
import { useI18n } from 'vue-i18n'
import { useCookies } from '@vueuse/integrations/useCookies'
import { jwtDecode } from 'jwt-decode'
import { Button } from '@/components/ui/button'
import { ref } from 'vue'

const { t } = useI18n()
const cookies = useCookies(['authorization', 'isardvdi_session'])

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

const username: typeof ref<string | null> = (() => {
  // TODO: Use const
  const savedBearer = cookies.get<string | undefined>('authorization') || cookies.get<string | undefined>('isardvdi_session')
  if (!savedBearer) {
    return null
  }

  const jwt = jwtDecode(savedBearer)
  // TODO: Use const
  if (jwt.type !== 'category-select') {
      return null
  }

  return jwt.user.username
})()

const logout = () => {
  cookies.remove('authorization')
  cookies.remove('isardvdi_session')
}
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
      {{ t('components.login.login-category-select.logged-in-as') }} <b>{{ username }}</b>
    </p>
    <Button class="mt-[8px]" hierarchy="link-color" @click="logout">{{ t('components.login.login-category-select.logged-in-as') }}</Button>
  </div>
</template>
