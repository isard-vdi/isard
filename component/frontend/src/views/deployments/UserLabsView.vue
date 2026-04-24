<script setup lang="ts">
import { getAllLabsApiV4ItemsLabsGetOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import LabCard from '@/components/card/LabCard.vue'
import Button from '@/components/ui/button/Button.vue'

const { t } = useI18n()
const queryClient = useQueryClient()
const router = useRouter()

const { isPending, isError, error, data } = useQuery(getAllLabsApiV4ItemsLabsGetOptions())
</script>
<template>
  <div v-if="!isPending" style="display: flex; flex-wrap: wrap; gap: 24px">
    <LabCard v-for="lab in data.labs" :key="lab.id" :lab="lab" />
  </div>
</template>
