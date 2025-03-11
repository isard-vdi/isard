<script lang="ts" setup>
import type { GetLoginConfigResponseNotification } from '@/gen/oas/api'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Icon } from '@/components/icon'
import { Button } from '@/components/ui/button'

interface Props {
  config: GetLoginConfigResponseNotification
}

const props = defineProps<Props>()
</script>

<template>
  <Alert
    class="bg-white border-gray-warm-300"
    :style="'white-space: pre-wrap; ' + props.config.extra_styles"
  >
    <Icon
      v-if="props.config.icon"
      :name="props.config.icon"
      class="rounded-[1px] outline outline-1 outline-offset-[10px] outline-gray-warm-300"
    />
    <AlertTitle v-if="props.config.title">{{ props.config.title }}</AlertTitle>
    <AlertDescription>
      <p v-if="props.config.description">{{ props.config.description }}</p>

      <Button
        v-if="props.config.button?.text && props.config.button?.url"
        hierarchy="link-color"
        class="p-0 mt-4"
        as="a"
        :href="props.config.button.url"
        :style="props.config.button.extra_styles"
        >{{ props.config.button.text }}</Button
      >
    </AlertDescription>
  </Alert>
</template>
