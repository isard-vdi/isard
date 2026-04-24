<script setup lang="ts">
import { AvatarLabel } from '@/components/avatar-label'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger
} from '@/components/ui/sidebar'
import { ref, computed } from 'vue'
import { type HTMLAttributes } from 'vue'
import { type PrimitiveProps } from 'reka-ui'
import { useCookies } from '@vueuse/integrations/useCookies'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { SIDEBAR_COOKIE_NAME } from '@/components/ui/sidebar/utils'
import { sidebarItemsContainer } from '.'
import SidebarItem from '@/components/sidebar/SidebarItem.vue'
import SidebarToggle from '@/components/sidebar/SidebarToggle.vue'
import type { SidebarItem as SidebarItemType } from '@/lib/navigation'
import type { UserResponse } from '@/gen/oas/apiv4/types.gen'
import LogoSvg from '@/assets/logo.svg?url'
import LogoCollapsedSvg from '@/assets/logo-collapsed.svg?url'

interface Props extends PrimitiveProps {
  items?: SidebarItemType[]
  footerItems?: SidebarItemType[]
  user: UserResponse
  loading?: boolean
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  as: 'button',
  items: () => [],
  footerItems: () => [],
  loading: false,
  class: ''
})

// Read the cookie to initialize the sidebar state correctly
const cookies = useCookies([SIDEBAR_COOKIE_NAME])
const cookieValue = cookies.get(SIDEBAR_COOKIE_NAME)
const open = ref(cookieValue === null || cookieValue === undefined ? true : Boolean(cookieValue))

const toggleSidebar = () => {
  open.value = !open.value
}

const activeSidebarItem = ref(props.items[0])

function setActiveSidebarItem(item: (typeof props.items)[number]) {
  activeSidebarItem.value = item
}

const emit = defineEmits(['logout'])

const { t } = useI18n()

const logoSrc = ref('/custom/logo.svg')
const logoCollapsedSrc = ref('/custom/logo-collapsed.svg')

const logoWidth = ref(0)
const logoHeight = ref(0)

const checkLogoDimensionas = (e) => {
  const img = e.target
  logoWidth.value = img.naturalWidth
  logoHeight.value = img.naturalHeight
}

// Logo sizing based on aspect ratio
const expandedLogoClass = computed(() => {
  if (!logoWidth.value || !logoHeight.value) return 'max-w-full max-h-15'
  const ratio = logoWidth.value / logoHeight.value
  if (ratio > 1.5) {
    return 'max-w-full'
  }
  return 'max-h-30'
})

const handleLogoError = () => {
  logoSrc.value = LogoSvg
}

const handleLogoCollapsedError = () => {
  logoCollapsedSrc.value = LogoCollapsedSvg
}
</script>

<template>
  <SidebarProvider v-model:open="open" class="w-auto">
    <Sidebar
      collapsible="icon"
      :class="[
        props.class,
        !open ? 'max-w-20 min-w-20 w-20' : 'max-w-72 min-w-72 w-72',
        'sticky border-gray-warm-300'
      ]"
    >
      <!-- Sidebar header -->
      <SidebarHeader class="md:pt-8 md:pb-2 px-6">
        <SidebarMenu>
          <SidebarMenuItem
            v-if="!open"
            class="flex flex-col items-center justify-center gap-6 h-full"
          >
            <img
              :src="logoCollapsedSrc"
              alt="IsardVDI"
              class="mx-auto hidden md:flex"
              @error="handleLogoCollapsedError"
            />
            <Tooltip>
              <TooltipTrigger as-child>
                <SidebarToggle :open="open" @click="toggleSidebar" />
              </TooltipTrigger>
              <TooltipContent side="right" :title="t('components.sidebar.expand')">
              </TooltipContent>
            </Tooltip>
          </SidebarMenuItem>
          <SidebarMenuItem v-else class="flex flex-row items-center justify-between min-h-26">
            <div class="flex items-center justify-center flex-1">
              <img
                :src="logoSrc"
                alt="IsardVDI Logo"
                :class="expandedLogoClass"
                @load="checkLogoDimensionas"
                @error="handleLogoError"
              />
            </div>
            <Tooltip>
              <TooltipTrigger as-child>
                <SidebarToggle
                  :open="open"
                  class="hidden md:flex shrink-0"
                  @click="toggleSidebar"
                />
              </TooltipTrigger>
              <TooltipContent side="right" :title="t('components.sidebar.collapse')">
              </TooltipContent>
            </Tooltip>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <!-- Sidebar scrollable content  -->
      <SidebarContent :class="cn(sidebarItemsContainer, !open && 'gap-8')">
        <div v-if="props.loading" class="flex flex-col items-center justify-start gap-6 mx-2">
          <Skeleton class="h-6 w-full" />
          <Skeleton class="h-6 w-full" />
          <Skeleton class="h-6 w-full" />
          <Skeleton class="h-6 w-full" />
        </div>
        <SidebarGroup v-else>
          <SidebarMenu>
            <SidebarItem
              v-for="item in props.items"
              :key="item.key"
              :icon="item.icon || ''"
              :label="item.label"
              :href="item.href"
              :route="item.route"
              :current="item.selected"
              :collapsed="!open"
              :sub-items="item.subItems"
              :selected="item.selected"
              :badge="item.badge"
              class="px-2 overflow-visible"
              @click="setActiveSidebarItem(item)"
            >
            </SidebarItem>
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <!-- Sidebar sticky footer -->
      <SidebarFooter>
        <div v-if="props.loading" class="flex flex-row items-center justify-start gap-2 mx-2">
          <Skeleton class="h-6 mb-2 w-full" />
        </div>
        <SidebarGroup v-else>
          <SidebarMenu>
            <SidebarItem
              v-for="item in props.footerItems"
              :key="item.key"
              :icon="item.icon || ''"
              :label="item.label"
              :href="item.href"
              :route="item.route"
              :current="item.selected"
              :collapsed="!open"
              :sub-items="item.subItems"
              :selected="item.selected"
              :badge="item.badge"
              class="overflow-visible"
              @click="setActiveSidebarItem(item)"
            >
            </SidebarItem>
          </SidebarMenu>
        </SidebarGroup>
        <!-- User info and logout -->
        <div class="px-4">
          <Separator color="gray-warm-400" orientation="horizontal" />
        </div>
        <SidebarMenu>
          <div
            v-if="props.loading"
            class="flex flex-row items-center mb-3 justify-start gap-2 mx-2"
          >
            <Skeleton class="mt-2 h-8 aspect-square rounded-full" />
            <Skeleton class="h-6 w-full" />
          </div>
          <SidebarMenuItem
            v-else
            :class="cn(sidebarItemsContainer, `gap-6 flex flex-${!open ? 'col' : 'row'}`)"
          >
            <Tooltip v-if="open">
              <TooltipTrigger as-child>
                <SidebarMenuButton as-child>
                  <RouterLink :to="{ name: 'profile' }">
                    <AvatarLabel
                      :src="user.photo || ''"
                      :name="user.name"
                      :sub="user.role_name"
                      size="md"
                      :fallback="
                        user.name
                          .split(' ')
                          .map((n: string) => n[0])
                          .join('')
                      "
                    />
                  </RouterLink>
                </SidebarMenuButton>
              </TooltipTrigger>
              <TooltipContent side="top" :title="t('components.sidebar.profile')"> </TooltipContent>
            </Tooltip>
            <Tooltip v-else>
              <TooltipTrigger as-child>
                <SidebarMenuButton
                  :tooltip="t('components.sidebar.profile')"
                  class="overflow-visible"
                  as-child
                >
                  <RouterLink :to="{ name: 'profile' }">
                    <Avatar size="md" class="mx-[-8px]">
                      <AvatarImage :src="user.photo || ''" :alt="user.name" />
                      <AvatarFallback>
                        {{
                          user.name
                            .split(' ')
                            .map((n: string) => n[0])
                            .join('')
                        }}
                      </AvatarFallback>
                    </Avatar>
                  </RouterLink>
                </SidebarMenuButton>
              </TooltipTrigger>
              <TooltipContent
                side="top"
                :class="!open ? 'hidden' : ''"
                :title="t('components.sidebar.profile')"
              >
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger as-child>
                <SidebarItem icon="log-out-01" :collapsed="!open" @click="emit('logout', $event)">
                </SidebarItem>
              </TooltipTrigger>
              <TooltipContent side="right" :title="t('components.sidebar.logout')">
              </TooltipContent>
            </Tooltip>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
    <!-- Header, trigger (only on mobile) and page content -->
    <SidebarInset class="w-1">
      <header
        class="flex-row z-50 sticky top-0 items-center px-8 py-6 bg-base-background border-b border-gray-warm-300 transition-[width,height] ease-in-out duration-75"
      >
        <div class="flex items-center gap-2 w-full">
          <SidebarTrigger class="cursor-pointer md:hidden" />
          <Separator orientation="vertical" color="gray-warm-300" class="mx-2 h-8 md:hidden" />
          <slot name="header" />
        </div>
      </header>
      <slot name="container" />
    </SidebarInset>
  </SidebarProvider>
</template>
