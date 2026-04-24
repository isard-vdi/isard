<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, toRaw } from 'vue'
import Button from '@/components/ui/button/Button.vue'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem
} from '@/components/ui/dropdown-menu'
import Icon from '@/components/icon/Icon.vue'

interface Props {
  menuContent: propsObjects[]
}

interface propsObjects {
  icon: string
  disabled?: boolean
  title?: string
  text: string
  onClick?: () => void
}

const props = defineProps<Props>()

const rawMenuContent = computed(() => toRaw(props.menuContent || []))
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger>
      <div class="bg-white border border-[#D7D3D0] rounded-lg p-2">
        <Icon size="lg" name="dots-vertical" />
      </div>
    </DropdownMenuTrigger>
    <DropdownMenuContent class="bg-white border border-[#D7D3D0] rounded-lg">
      <DropdownMenuGroup>
        <DropdownMenuItem v-for="item in rawMenuContent" :key="item.text">
          <Button
            v-bind="item"
            class="mr-2"
            hierarchy="link-gray"
            icon-size="md"
            @click="item.onClick"
          >
            {{ item.text }}
          </Button>
        </DropdownMenuItem>
      </DropdownMenuGroup>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
