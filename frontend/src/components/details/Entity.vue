<template>
  <div class="p-grid p-fluid">
    <div class="p-col-12 p-md-12">
      <div class="card">
        <h2>Entity Detail</h2>
        <div class="p-grid p-formgrid">
          <isard-input-text
            id="entityid"
            v-model="entity.id"
            type="text"
            placeholder="ID"
            :disabled="true"
            label="ID"
          ></isard-input-text>

          <isard-input-text
            id="entityname"
            v-model="entity.name"
            type="text"
            placeholder="Name"
            :disabled="!editMode"
            label="Name"
          ></isard-input-text>

          <isard-input-text
            id="entityuuid"
            v-model="entity.uuid"
            type="text"
            placeholder="UUID"
            :disabled="!editMode"
            class="p-error"
            label="UUID"
          ></isard-input-text>
        </div>
      </div>
      <br />
      <h4>Users</h4>
      <div class="card">
        <div class="p-grid p-formgrid">
          <DataTable :value="entity.users">
            <Column field="name" header="Name"></Column>
            <Column field="surname" header="Surname"></Column>
            <Column field="UUID" header="uuid"></Column>
          </DataTable>
        </div>
      </div>
      <main-form-buttons
        :edit-enabled="editEnabled"
        :form-changed="formChanged"
        @savebuttonPressed="saveItem"
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

export default defineComponent({
  setup() {
    const store = useStore();
    const entity = reactive(cloneDeep(store.getters.detail));
    const editMode: ComputedRef<any> = computed(() => store.getters.editMode);
    const editEnabled = true;

    const formChanged: ComputedRef<boolean> = computed(
      () => JSON.stringify(entity) !== JSON.stringify(store.getters.detail)
    );

    function saveItem(): void {
      const persistenceObject = UpdateUtils.getUpdateObject(
        cloneDeep(entity),
        cloneDeep(store.getters.detail)
      );

      const payload = { persistenceObject };
      store.dispatch(ActionTypes.SAVE_ITEM, payload);
    }

    return {
      entity,
      formChanged,
      editEnabled,
      editMode,
      saveItem
    };
  },
  data() {
    return {};
  }
});
</script>
