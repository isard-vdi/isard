<template>
  <div>
    <h5>Menu Type</h5>
    <div class="p-formgroup-inline">
      <Button label="Change menu type" @click="f_changeMenuType" />
    </div>

    <h5>Menu Color</h5>
    <div class="p-formgroup-inline">
      <Button label="Change menu color" @click="f_changeMenuColorMode" />
    </div>
  </div>
</template>

<script>
import { useStore } from '@/store';
import { computed } from 'vue';
import { ActionTypes } from '@/store/actions';

export default {
  setup() {
    const store = useStore();

    const menuType = computed(() => store.getters.menuType);

    const menuColorMode = computed(() => store.getters.menuColorMode);

    const f_changeMenuType = () => {
      if (store.getters.menuVisible) store.dispatch(ActionTypes.TOGGLE_MENU);

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
  },
};
</script>
