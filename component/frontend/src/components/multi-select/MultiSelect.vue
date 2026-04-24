<script setup lang="ts">
import {
  Combobox,
  ComboboxAnchor,
  ComboboxEmpty,
  ComboboxGroup,
  ComboboxInput,
  ComboboxItem,
  ComboboxList
} from '@/components/ui/combobox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Label } from '@/components/ui/label'
import { useI18n } from 'vue-i18n'
import { type MultiSelectTagItemType as Tag, MultiSelectSelectedItem } from '.'
import { ref, watch, onMounted } from 'vue'
import { Icon } from '@/components/icon'
import { useFilter } from 'reka-ui'
import { computed } from 'vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'

const { t } = useI18n()
interface Props {
  tags: Tag[]
  preselectedTags?: Tag[] | undefined
  label: string
  placeholder: string
  notFoundText?: string
  loading?: boolean
}
const props = withDefaults(defineProps<Props>(), {
  preselectedTags: undefined,
  notFoundText: '',
  loading: false
})

const notFoundMessage = computed<string>(
  () => props.notFoundText || t('components.multiselect.not-found')
)

const emit = defineEmits<(e: 'update:selected-tags', selectedTags: Tag[]) => void>()

const selectedTags = ref<Tag[]>([])

watch(
  selectedTags,
  (newVal) => {
    emit('update:selected-tags', newVal)
  },
  { deep: true }
)

// Modify the preselectedTags watcher to prevent circular updates
watch(
  () => props.preselectedTags,
  (newVal, oldVal) => {
    if (newVal && JSON.stringify(newVal) !== JSON.stringify(selectedTags.value)) {
      selectedTags.value = [...newVal]
    }
  },
  { immediate: true, deep: true }
)

const searchTerm = ref('')

const { contains } = useFilter({ sensitivity: 'base' })
const filteredTags = computed(() => {
  // const options = props.tags.filter(i => !selectedTags.value.includes(i))
  const options = props.tags
  return searchTerm.value
    ? options.filter(
        (option) => contains(option.label, searchTerm.value)
        // TODO: Commented due to performance issues
        // contains(option.label, searchTerm.value) ||
        // contains(option.id, searchTerm.value) ||
        // (option.subLabel && contains(option.subLabel, searchTerm.value))
      )
    : options
})

onMounted(() => {
  // Set initial selection if provided via v-model
  if (Array.isArray(props.preselectedTags) && props.preselectedTags.length > 0) {
    selectedTags.value = [...props.preselectedTags]
  }
})
</script>

<template>
  <div class="flex flex-col gap-4 h-full w-full">
    <Combobox by="label" class="w-full" :ignore-filter="true">
      <Label class="" for="frameworks">{{ props.label }}</Label>
      <ComboboxAnchor class="w-full">
        <div class="relative w-full items-center">
          <ComboboxInput
            v-model="searchTerm"
            class="pl-9 bg-base-white"
            :display-value="(val) => val?.label ?? ''"
            :placeholder="props.placeholder"
          />
          <span class="absolute start-0 inset-y-0 flex items-center justify-center px-3">
            <Icon name="search-sm" size="sm" stroke-color="text-gray-warm-500" />
          </span>
        </div>
      </ComboboxAnchor>

      <ComboboxList class="w-(--reka-popper-anchor-width)">
        <ComboboxEmpty>{{ notFoundMessage }}</ComboboxEmpty>

        <ScrollArea>
          <div class="max-h-[300px]">
            <ComboboxGroup class="flex flex-col gap-1">
              <ComboboxItem
                v-for="tag in filteredTags"
                :key="tag.id"
                :value="tag"
                class="justify-start text-gray-warm-900 font-medium"
                :class="
                  selectedTags.some((t) => t.id === tag.id)
                    ? 'bg-brand-100 data-highlighted:bg-brand-200'
                    : ''
                "
                @select.prevent="
                  (ev) => {
                    if (typeof ev.detail.value === 'string') {
                      selectedTags = selectedTags.filter((tag) => tag.id !== tag.id)
                    } else {
                      if (!selectedTags.some((t) => t.id === tag.id)) {
                        selectedTags.push(tag)
                      } else {
                        selectedTags = selectedTags.filter((t) => t.id !== tag.id)
                      }
                    }
                  }
                "
              >
                <template v-if="false">
                  <Checkbox :checked="selectedTags.some((t) => t.id === tag.id)" class="shrink-0" />
                </template>

                <Icon v-if="tag.icon !== undefined" :name="tag.icon" size="md" class="shrink-0" />
                <Avatar v-if="tag.avatar !== undefined" size="xs" class="shrink-0">
                  <AvatarImage :src="tag.avatar" :alt="tag.id" />
                  <AvatarFallback>
                    {{
                      tag.label
                        .split(' ')
                        .map((n) => n[0])
                        .join('')
                    }}
                  </AvatarFallback>
                </Avatar>

                <span class="text-nowrap text-ellipsis overflow-hidden">
                  {{ tag.label }}
                </span>

                <span v-if="tag.subLabel" class="text-gray-warm-600 font-normal">
                  {{ tag.subLabel }}
                </span>

                <Icon
                  v-if="true && selectedTags.some((t) => t.id === tag.id)"
                  name="check"
                  size="sm"
                  class="ml-auto shrink-0"
                />
              </ComboboxItem>
            </ComboboxGroup>
          </div>
        </ScrollArea>
      </ComboboxList>
    </Combobox>

    <ScrollArea class="h-full bg-transparent rounded-md">
      <div v-if="props.loading" class="flex flex-col gap-2">
        <Skeleton class="h-6" />
        <Skeleton class="h-6" />
        <Skeleton class="h-6" />
      </div>
      <div v-else class="flex flex-col gap-1">
        <MultiSelectSelectedItem
          v-for="tag in selectedTags"
          :id="tag.id"
          :key="tag.id"
          :label="tag.label"
          :sub-label="tag.subLabel"
          :avatar="tag.avatar"
          :icon="tag.icon"
          @remove-tag="
            (id) => {
              selectedTags = selectedTags.filter((tag) => tag.id !== id)
            }
          "
        />
      </div>
    </ScrollArea>
  </div>
</template>
