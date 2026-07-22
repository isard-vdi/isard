<script setup lang="ts">
import { defineModel, onMounted, watch } from 'vue'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem
} from '@/components/ui/select'
import { Locale, i18n, setLocale } from '@/lib/i18n'

const locale = defineModel<Locale>({
  default: i18n.global.locale.value as Locale,
  set(newLocale) {
    setLocale(newLocale)
    localStorage.language = newLocale

    return newLocale
  }
})

// Ensure the sync between the switch and the locale
onMounted(() => {
  locale.value = i18n.global.locale.value as Locale
})

watch(i18n.global.locale, (newI18n) => {
  if (locale.value !== newI18n) {
    locale.value = newI18n as Locale
  }
})
</script>

<template>
  <Select v-model="locale">
    <SelectTrigger>
      <SelectValue placeholder="Select language" />
    </SelectTrigger>
    <SelectContent>
      <SelectGroup>
        <SelectItem v-for="(id, name) in Locale" :key="id" :value="id">{{ name }}</SelectItem>
      </SelectGroup>
    </SelectContent>
  </Select>
</template>
