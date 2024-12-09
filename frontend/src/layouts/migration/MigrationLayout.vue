<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import Button from '@/components/ui/button/Button.vue';

const { t } = useI18n()


interface Props {
  goBack: boolean
}

const props = withDefaults(defineProps<Props>(), {
  goBack: false
})

const goToDesktops = () => {
  window.location.pathname = '/'
}
</script>

<template>
  <div class="flex h-screen min-h-screen overflow-y-auto bg-base-background">
    <div class="w-full md:w-full h-full min-h-screen p-[32px] flex flex-col justify-between overflow-y-auto">
      <div class="h-full self-center flex flex-col w-full z-20">
        <template v-if="props.goBack">
          <Button icon="arrow-left" hierarchy="link-color" class="text-lg w-min absolute" @click="goToDesktops">
            {{ t('layouts.single-page.go-back') }}
          </Button>
        </template>
        <slot name="title" />
        <div>
          <slot name="main" />
        </div>
      </div>
    </div>
  </div>
  <img src="@/assets/img/clouds.svg" alt="asdasd" class="fixed top-[75px] left-[100px] z-10">
  <img src="@/assets/img/mountains.svg" alt="asdasd" class="fixed bottom-0 right-0 z-10">
</template>
