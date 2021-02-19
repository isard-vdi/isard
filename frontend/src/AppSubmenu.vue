<template>
  <ul v-if="items">
    <template v-for="(item, i) of items">
      <li
        v-if="visible(item) && !item.separator"
        :key="i"
        :class="[
          { 'active-menuitem': activeIndex === i && !item.to && !item.disabled }
        ]"
        role="none"
      >
        <div v-if="item.items && root === true" class="arrow"></div>
        <router-link
          v-if="item.to"
          :to="item.to"
          :class="[
            item.class,
            { 'active-route': activeIndex === i, 'p-disabled': item.disabled }
          ]"
          :style="item.style"
          :target="item.target"
          exact
          role="menuitem"
        >
          <div @click="onMenuItemClick($event, item, i)">
            <i :class="item.icon"></i>
            <span>{{ item.label }}</span>
            <i
              v-if="item.items"
              class="pi pi-fw pi-angle-down menuitem-toggle-icon"
            ></i>
            <span v-if="item.badge" class="menuitem-badge"
              >{{ item.badge }}
            </span>
          </div>
        </router-link>
        <a
          v-else
          :href="item.url || '#'"
          :style="item.style"
          :class="[item.class, { 'p-disabled': item.disabled }]"
          :target="item.target"
          role="menuitem"
          @click="onMenuItemClick($event, item, i)"
        >
          <i :class="item.icon"></i>
          <span>{{ item.label }}</span>
          <i
            v-if="item.items"
            class="pi pi-fw pi-angle-down menuitem-toggle-icon"
          ></i>
          <span v-if="item.badge" class="menuitem-badge">{{ item.badge }}</span>
        </a>
        <transition name="layout-submenu-wrapper">
          <AppSubmenu
            v-show="activeIndex === i"
            :items="visible(item) && item.items"
          ></AppSubmenu>
        </transition>
      </li>
      <li
        v-if="visible(item) && item.separator"
        :key="'separator' + i"
        class="p-menu-separator"
        :style="item.style"
        role="separator"
      ></li>
    </template>
  </ul>
</template>
<script>
export default {
  name: 'AppSubmenu',
  props: {
    items: {
      type: Array
    },
    root: {
      type: Boolean,
      default: false
    }
  },
  data() {
    return {
      activeIndex: null
    };
  },
  methods: {
    onMenuItemClick(event, item, index) {
      if (item.disabled) {
        event.preventDefault();
        return;
      }

      if (!item.to && !item.url) {
        event.preventDefault();
      }

      //execute command
      if (item.command) {
        item.command({ originalEvent: event, item: item });
      }

      this.activeIndex = index === this.activeIndex ? null : index;
    },
    visible(item) {
      return typeof item.visible === 'function'
        ? item.visible()
        : item.visible !== false;
    }
  }
};
</script>

<style scoped></style>
