<script setup lang="ts">
import { Primitive, type PrimitiveProps } from 'radix-vue'
import {
  NavigationMenu,
  NavigationMenuLink,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuTrigger,
  NavigationMenuContent,
  NavigationMenuViewport
} from '@/components/ui/navigation-menu'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { type HTMLAttributes } from 'vue'
import { Icon } from '@/components/icon'
import { useRoute, RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'

interface Props extends PrimitiveProps {
  items?: MenuItemType[]
  user: UserInfo
  isConnected: boolean
  loading?: boolean
  class?: HTMLAttributes['class']
}
const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  loading: false
})

interface UserInfo {
  name: string
  role: string
  img: string
}

interface MenuItemType {
  label: string
  href: string
  icon?: string
  active?: boolean
}

const route = useRoute()

const isActive = (to: string) => {
  return route.name === to
}

const { t } = useI18n()
</script>

<template>
  <div :class="props.class">
    <NavigationMenu :items="items">
      <NavigationMenuList>
        <NavigationMenuItem
          v-for="(item, index) in items"
          :key="index"
          :icon="item.icon"
          :label="item.label"
          :href="item.href"
          class="text-gray-warm-400"
          icon-stroke-color="error-500"
        >
          <NavigationMenuLink
            v-if="!item.subItems && item.href"
            :href="item.href"
            class="flex items-center gap-2 px-4 py-2"
          >
            <slot>
              <Icon v-if="item.icon" :name="item.icon" size="xl" stroke-color="gray-warm-400" />
              <span>{{ item.label }}</span>
            </slot>
          </NavigationMenuLink>
          <RouterLink
            v-else-if="item.to"
            :to="{ name: item.to }"
            class="flex items-center gap-2 px-4 py-2"
            :class="{
              'text-white': isActive(item.to),
              'text-muted-foreground hover:bg-muted': !isActive(item.to)
            }"
          >
            <slot>
              <Icon
                v-if="item.icon"
                :name="item.icon"
                size="xl"
                :stroke-color="isActive(item.to) ? 'base-white' : 'gray-warm-400'"
              />
              <span :class="{ 'font-bold': isActive(item.to) }">{{ item.label }}</span>
            </slot>
          </RouterLink>
          <template v-else>
            <NavigationMenuTrigger class="flex items-center gap-2 px-4 py-2">
              <slot>
                <Icon v-if="item.icon" :name="item.icon" size="xl" stroke-color="gray-warm-400" />
                <span>{{ item.label }}</span>
              </slot>
            </NavigationMenuTrigger>
            <NavigationMenuContent>
              <ul>
                <li v-for="subitem in item.subItems" :key="subitem.label" class="row-span-3">
                  <NavigationMenuLink as-child>
                    <a
                      class="flex h-full w-full select-none flex-col justify-end rounded-md bg-linear-to-b from-muted/50 to-muted p-6 no-underline outline-hidden focus:shadow-md"
                      :href="subitem.href"
                    >
                      <Icon v-if="subitem.icon" :name="subitem.icon" size="xl" class="mr-1" />
                      <slot>
                        <span>{{ subitem.label }}</span>
                      </slot>
                    </a>
                  </NavigationMenuLink>
                </li>
              </ul>
            </NavigationMenuContent>
          </template>
        </NavigationMenuItem>
      </NavigationMenuList>
    </NavigationMenu>
    <NavigationMenu>
      <NavigationMenuList>
        <NavigationMenuItem>
          <NavigationMenuTrigger
            :title="
              isConnected
                ? t('components.sidebar.websockets-on')
                : t('components.sidebar.websockets-off')
            "
          >
            <div class="flex items-center gap-2">
              <Avatar>
                <AvatarImage :src="user.img" :alt="user.name" />
                <AvatarFallback>
                  {{
                    user.name
                      .split(' ')
                      .map((n) => n[0])
                      .join('')
                  }}
                </AvatarFallback>
              </Avatar>
              <div class="text-gray-warm-400 hidden sm:block">
                <span>{{ user.name }}</span>
                <span class="text-gray-warm-400 text-sm ml-1"> [{{ user.role }}] </span>
              </div>
              <Icon
                :name="isConnected ? 'zap-circle' : 'x-circle'"
                :stroke-color="isConnected ? 'success-600' : 'error-600'"
                size="md"
              />
            </div>
          </NavigationMenuTrigger>
          <NavigationMenuContent>
            <ul class="grid w-[200px] gap-1 p-2">
              <li>
                <NavigationMenuLink as-child>
                  <RouterLink
                    to="/profile"
                    class="flex items-center gap-2 px-4 py-2 rounded-md hover:bg-muted"
                  >
                    <Icon name="user-03" />
                    <span>{{ t('components.sidebar.profile') }}</span>
                  </RouterLink>
                </NavigationMenuLink>
              </li>
              <li>
                <NavigationMenuLink as-child>
                  <a
                    href="#"
                    class="flex items-center gap-2 px-4 py-2 rounded-md hover:bg-muted"
                    @click.prevent="logout"
                  >
                    <Icon name="log-out-01" />
                    <span>{{ t('components.sidebar.logout') }}</span>
                  </a>
                </NavigationMenuLink>
              </li>
            </ul>
          </NavigationMenuContent>
        </NavigationMenuItem>
      </NavigationMenuList>
    </NavigationMenu>
  </div>
</template>
