<template>
  <div class="p-grid p-fluid">
    <div class="p-col-12 p-md-12">
      <div class="card">
        <h2>Desktop Detail</h2>
        <div class="p-grid p-formgrid">
          <isard-input-text
            id="id"
            v-model="desktop.id"
            type="text"
            placeholder="ID"
            :disabled="true"
            label="ID"
          ></isard-input-text>

          <isard-input-text
            id="name"
            v-model="desktop.name"
            type="text"
            placeholder="Name"
            :disabled="!editMode && !createMode"
            label="Name"
          ></isard-input-text>

          <isard-input-text
            id="description"
            v-model="desktop.description"
            type="text"
            placeholder="Decription"
            :disabled="!editMode && !createMode"
            label="Description"
          ></isard-input-text>

          <isard-input-text
            id="uuid"
            v-model="desktop.uuid"
            type="text"
            placeholder="UUID"
            :disabled="!editMode && !createMode"
            class="p-error"
            label="UUID"
          ></isard-input-text>
        </div>
      </div>
      <br />

      <main-form-buttons
        :edit-enabled="editEnabled"
        :form-changed="formChanged"
        :create-mode="createMode"
        @savebuttonPressed="f_saveItem"
        @savenewbuttonPressed="f_saveNewItem"
      />
    </div>
  </div>
</template>

<script lang="ts">
import { computed, ComputedRef, defineComponent, reactive } from 'vue';
import { useStore } from '@/store';
import { cloneDeep } from 'lodash';
import UpdateUtils from '@/utils/UpdateUtils';
import { ActionTypes } from '@/store/actions';
import IsardInputText from '@/components/shared/forms/IsardInputText.vue';

export default defineComponent({
  components: {
    IsardInputText: IsardInputText
  },
  setup() {
    const store = useStore();
    const desktop = reactive(cloneDeep(store.getters.detail));
    const editMode: ComputedRef<any> = computed(() => store.getters.editMode);
    const createMode: ComputedRef<any> = computed(
      () => store.getters.createMode
    );
    const editEnabled = true;

    const formChanged: ComputedRef<boolean> = computed(
      () => JSON.stringify(desktop) !== JSON.stringify(store.getters.detail)
    );

    function f_saveItem(): void {
      let persistenceObject = UpdateUtils.getUpdateObject(
        cloneDeep(desktop),
        cloneDeep(store.getters.detail)
      );

      persistenceObject.id = desktop.id;

      const payload = { persistenceObject };
      store.dispatch(ActionTypes.SAVE_ITEM, payload);
    }

    function f_saveNewItem(): void {
      const persistenceObject = cloneDeep(desktop);

      const payload = { persistenceObject };
      store.dispatch(ActionTypes.SAVE_NEW_ITEM, payload);
    }

    return {
      desktop,
      formChanged,
      editEnabled,
      editMode,
      createMode,
      f_saveItem,
      f_saveNewItem
    };
  }
});
</script>
