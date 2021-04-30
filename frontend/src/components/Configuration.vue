<template>
  <div>
    <h5>{{ $t('views.config.menu-type.label') }}</h5>
    <div class="p-formgroup-inline">
      <Button
        :label="
          $t('views.config.button', {
            option: $t('views.config.menu-type.option')
          })
        "
        @click="f_changeMenuType"
      />
    </div>

    <h5>{{ $t('views.config.menu-color.label') }}</h5>
    <div class="p-formgroup-inline">
      <Button
        :label="
          $t('views.config.button', {
            option: $t('views.config.menu-color.option')
          })
        "
        @click="f_changeMenuColorMode"
      />
    </div>
  </div>
</template>

<script>
import { useStore } from '@/store';
import { computed } from 'vue';
import { ActionTypes } from '@/store/actions';
import Button from 'primevue/button';

export default {
  components: {
    Button: Button
  },
  setup() {
    const store = useStore();

    const menuType = computed(() => store.getters.menuType);

    const menuColorMode = computed(() => store.getters.menuColorMode);

    const f_changeMenuType = () => {
      if (store.getters.isMenuVisible) store.dispatch(ActionTypes.TOGGLE_MENU);

      store.dispatch(
        ActionTypes.CHANGE_MENU_TYPE,
        store.getters.menuType === 'static' ? 'overlay' : 'static'
      );
    };

    const f_changeMenuColorMode = () => {
      store.dispatch(
        ActionTypes.CHANGE_MENU_COLOR_MODE,
        store.getters.menuColorMode === 'dark' ? 'light' : 'dark'
      );
    };

    return {
      menuType,
      menuColorMode,
      f_changeMenuType,
      f_changeMenuColorMode
    };
  }
};
</script>
