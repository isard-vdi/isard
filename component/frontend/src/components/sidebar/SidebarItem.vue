<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'
import { Icon } from '@/components/icon'
import {
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarMenuButton,
  SidebarMenuItem
} from '@/components/ui/sidebar'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { type SidebarItem, type Badge } from '@/lib/navigation'
import { sidebarItemVariants } from '@/components/sidebar'
import { cn } from '@/lib/utils'

interface Props {
  icon: string
  label?: string
  route?: string
  href?: string
  collapsed?: boolean
  badge?: Badge
  class?: HTMLAttributes['class']
  subItems?: SidebarItem[] | undefined
  selected?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  label: '',
  route: '',
  href: '',
  badge: undefined,
  class: '',
  subItems: undefined,
  selected: false
})

const isActive = computed(() => props.selected)
const iconStrokeColor = computed(() => (isActive.value ? 'secondary-2-500' : 'gray-warm-500'))
</script>

<template>
  <!-- Collapsed mode: use dropdown menu to show sub-items -->
  <DropdownMenu v-if="props.subItems && props.collapsed">
    <SidebarMenuItem>
      <DropdownMenuTrigger as-child>
        <SidebarMenuButton
          :is-active="isActive"
          :tooltip="props.label"
          :class="
            cn(
              'w-full',
              isActive
                ? '!font-extrabold !text-gray-warm-800'
                : '!font-semibold !text-gray-warm-600'
            )
          "
        >
          <Icon :name="props.icon" size="lg" :stroke-color="iconStrokeColor" />
        </SidebarMenuButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side="right"
        align="start"
        class="min-w-48 bg-sidebar border-gray-warm-300 p-2"
      >
        <DropdownMenuLabel class="text-base leading-6 font-bold text-gray-warm-800 px-3 py-2">
          {{ props.label }}
        </DropdownMenuLabel>
        <DropdownMenuSeparator class="bg-gray-warm-300" />
        <DropdownMenuItem
          v-for="subItem in props.subItems"
          :key="subItem.key"
          as-child
          :class="
            cn(
              'rounded-sm px-3 py-2 text-base leading-6 cursor-pointer',
              subItem.selected
                ? 'bg-base-menu-current !font-extrabold !text-gray-warm-800'
                : 'bg-transparent !font-semibold !text-gray-warm-600 hover:bg-base-menu-current/50'
            )
          "
        >
          <RouterLink
            v-if="subItem.route"
            :to="{ name: subItem.route }"
            class="flex items-center gap-2"
          >
            <Icon
              v-if="subItem.icon"
              :name="subItem.icon"
              size="lg"
              :stroke-color="subItem.selected ? 'secondary-2-500' : 'gray-warm-500'"
            />
            <span class="leading-6 text-base truncate">{{ subItem.label }}</span>
          </RouterLink>
          <a v-else :href="subItem.href" class="flex items-center gap-2">
            <Icon
              v-if="subItem.icon"
              :name="subItem.icon"
              size="lg"
              :stroke-color="subItem.selected ? 'secondary-2-500' : 'gray-warm-500'"
            />
            <span class="leading-6 text-base truncate">{{ subItem.label }}</span>
          </a>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </SidebarMenuItem>
  </DropdownMenu>
  <!-- Expanded mode: use collapsible to show sub-items inline -->
  <Collapsible v-else-if="props.subItems" as-child class="group/collapsible">
    <SidebarMenuItem>
      <CollapsibleTrigger as-child>
        <SidebarMenuButton
          :is-active="isActive"
          :tooltip="props.label"
          :class="
            cn(
              'w-full',
              isActive
                ? '!font-extrabold !text-gray-warm-800'
                : '!font-semibold !text-gray-warm-600'
            )
          "
        >
          <Icon :name="props.icon" size="lg" :stroke-color="iconStrokeColor" />
          <p
            v-if="label"
            :class="[
              'leading-6 text-base flex-1 truncate',
              isActive
                ? '!font-extrabold !text-gray-warm-800'
                : '!font-semibold !text-gray-warm-600'
            ]"
          >
            {{ props.label }}
          </p>
          <div
            v-if="badge !== undefined"
            class="px-2 py-0.5 bg-gray-50 rounded-2xl outline outline-2 outline-sidebar flex justify-start items-center"
          >
            <div class="text-center text-slate-700 text-xs font-medium leading-4 cursor-pointer">
              {{ badge }}
            </div>
          </div>
          <Icon
            name="chevron-down"
            size="md"
            :stroke-color="iconStrokeColor"
            class="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-180"
          />
        </SidebarMenuButton>
      </CollapsibleTrigger>
      <!-- TODO: Allow multiple level nesting. For now only one level -->
      <CollapsibleContent>
        <SidebarMenuSub class="gap-1">
          <SidebarMenuSubItem
            v-for="subItem in props.subItems"
            :key="subItem.key"
            :class="
              cn(
                subItem.selected
                  ? '!font-extrabold !text-gray-warm-800'
                  : '!font-semibold !text-gray-warm-600',
                'w-full',
                subItem.selected
                  ? '!font-extrabold !text-gray-warm-800'
                  : '!font-semibold !text-gray-warm-600'
              )
            "
          >
            <SidebarMenuSubButton
              v-if="subItem.route"
              as-child
              class="p-2"
              :is-active="subItem.selected"
            >
              <RouterLink
                v-if="subItem.route"
                :to="{ name: subItem.route }"
                class="flex items-center gap-2"
              >
                <Icon
                  v-if="subItem.icon"
                  :name="subItem.icon"
                  size="lg"
                  :stroke-color="subItem.selected ? 'secondary-2-500' : 'gray-warm-500'"
                />
                <p class="leading-6 text-base truncate">
                  {{ subItem.label }}
                </p>
              </RouterLink>
            </SidebarMenuSubButton>
            <SidebarMenuSubButton
              v-else
              :href="subItem.href"
              class="gap-2"
              :is-active="subItem.selected"
            >
              <Icon
                v-if="subItem.icon"
                :name="subItem.icon"
                size="lg"
                :stroke-color="subItem.selected ? 'secondary-2-500' : 'gray-warm-500'"
              />
              <p class="leading-6 text-base truncate">
                {{ subItem.label }}
              </p>
            </SidebarMenuSubButton>
          </SidebarMenuSubItem>
        </SidebarMenuSub>
      </CollapsibleContent>
    </SidebarMenuItem>
  </Collapsible>
  <SidebarMenuItem
    v-else
    :class="isActive ? '!font-extrabold !text-gray-warm-800' : '!font-semibold !text-gray-warm-600'"
  >
    <SidebarMenuButton
      :is-active="isActive"
      :tooltip="props.label"
      as-child
      :class="
        cn(
          sidebarItemVariants({ selected: isActive }),
          props.class,
          isActive ? '!font-extrabold !text-gray-warm-800' : '!font-semibold !text-gray-warm-600',
          props.collapsed ? ' mb-2' : ''
        )
      "
    >
      <RouterLink
        v-if="props.route"
        :to="{ name: props.route }"
        :class="cn('flex items-center', !props.collapsed && 'gap-2')"
      >
        <div class="relative">
          <Icon :name="props.icon" size="lg" :stroke-color="iconStrokeColor" class="relative" />
          <div
            v-if="badge !== undefined && props.collapsed && badge.label > 0"
            :class="`absolute top-3 left-3 px-2 py-0.5 rounded-2xl outline outline-2 outline-sidebar flex justify-start items-center ${badge.bgColor}`"
          >
            <div
              :class="`'text-center text-xs font-medium leading-4 cursor-pointer ${badge.textColor}`"
            >
              {{ badge.label }}
            </div>
          </div>
        </div>
        <p
          v-if="label && !props.collapsed"
          :class="[
            'leading-6 text-base flex-1 truncate',
            isActive ? '!font-extrabold !text-gray-warm-800' : '!font-semibold !text-gray-warm-600'
          ]"
        >
          {{ props.label }}
        </p>
        <div
          v-if="badge !== undefined && !props.collapsed"
          class="px-2 py-0.5 bg-gray-50 rounded-2xl outline outline-2 outline-sidebar flex justify-start items-center"
        >
          <div class="text-center text-slate-700 text-xs font-medium leading-4 cursor-pointer">
            {{ badge.label }}
          </div>
        </div>
      </RouterLink>
      <a v-else :href="props.href" :class="cn('flex items-center', !props.collapsed && 'gap-2')">
        <div class="relative">
          <Icon :name="props.icon" size="lg" :stroke-color="iconStrokeColor" class="relative" />
          <div
            v-if="badge !== undefined && props.collapsed && badge.label > 0"
            :class="`absolute top-3 left-3 px-2 py-0.5 rounded-2xl outline outline-2 outline-sidebar flex justify-start items-center ${badge.bgColor}`"
          >
            <div
              :class="`'text-center text-xs font-medium leading-4 cursor-pointer ${badge.textColor}`"
            >
              {{ badge.label }}
            </div>
          </div>
        </div>
        <p
          v-if="label && !props.collapsed"
          :class="[
            'leading-6 text-base flex-1 truncate',
            isActive ? '!font-extrabold !text-gray-warm-800' : '!font-semibold !text-gray-warm-600'
          ]"
        >
          {{ props.label }}
        </p>
        <div
          v-if="badge !== undefined && !props.collapsed"
          :class="`px-2 py-0.5 rounded-2xl outline outline-2 outline-sidebar flex justify-start items-center ${badge.bgColor}`"
        >
          <div
            :class="`'text-center text-xs font-medium leading-4 cursor-pointer ${badge.textColor}`"
          >
            {{ badge.label }}
          </div>
        </div>
      </a>
    </SidebarMenuButton>
  </SidebarMenuItem>
</template>
