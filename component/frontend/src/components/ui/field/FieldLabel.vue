<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'
import { useI18n } from 'vue-i18n'
import { cn } from '@/lib/utils'
import { Label } from '@/components/ui/label'
import { useFormSchema } from '@/composables/useFormSchema'
import { isFieldRequired } from '@/lib/zod-required'

const props = withDefaults(
  defineProps<{
    class?: HTMLAttributes['class']
    for?: string // Id of the control this label names
    required?: boolean // Overrides the schema lookup
  }>(),
  {
    class: undefined,
    for: undefined,
    required: undefined
  }
)

const { t } = useI18n()
const formSchema = useFormSchema()

const showRequired = computed(() => props.required ?? isFieldRequired(formSchema.value, props.for))
</script>

<template>
  <Label
    data-slot="field-label"
    :for="props.for"
    :class="
      cn(
        'group/field-label peer/field-label flex w-fit gap-2 leading-snug group-data-[disabled=true]/field:opacity-50',
        'has-[>[data-slot=field]]:w-full has-[>[data-slot=field]]:flex-col has-[>[data-slot=field]]:rounded-md has-[>[data-slot=field]]:border [&>*]:data-[slot=field]:p-4',
        'has-data-[state=checked]:bg-primary/5 has-data-[state=checked]:border-primary dark:has-data-[state=checked]:bg-primary/10',
        props.class
      )
    "
  >
    <slot />
    <!-- `-ms-1` trims the label's own `gap-2` down to a single space. -->
    <span v-if="showRequired" data-slot="field-required" class="-ms-1">
      <span aria-hidden="true" class="text-gray-warm-500">{{
        t('components.form.required.marker')
      }}</span>
      <!-- A non-breaking space: the accessible name concatenates both spans
           without a separator, and the compiler condenses a plain one away. -->
      <span class="sr-only">&nbsp;{{ t('components.form.required.text') }}</span>
    </span>
  </Label>
</template>
