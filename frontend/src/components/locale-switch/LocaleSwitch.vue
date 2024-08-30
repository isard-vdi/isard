<script setup lang="ts">
import { defineModel } from 'vue'
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
  default: i18n.global.locale.value,
  set(newLocale) {
    setLocale(i18n, newLocale)

    return newLocale
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
