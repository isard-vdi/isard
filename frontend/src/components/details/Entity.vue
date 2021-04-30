<template>
  <div class="p-grid p-fluid">
    <div class="p-col-12 p-md-12">
      <div class="card">
        <h2>{{ $t('detail.headers.entity') }}</h2>
        <div class="p-grid p-formgrid">
          <isard-input-text
            id="id"
            v-model="entity.id"
            type="text"
            :placeholder="$t('detail.fields.id.placeholder')"
            :disabled="true"
            :label="$t('detail.fields.id.label')"
          ></isard-input-text>

          <isard-input-text
            id="name"
            v-model="entity.name"
            type="text"
            :placeholder="$t('detail.fields.name.placeholder')"
            :disabled="!editMode && !createMode"
            :label="$t('detail.fields.name.label')"
          ></isard-input-text>

          <isard-input-text
            id="description"
            v-model="entity.description"
            type="text"
            :placeholder="$t('detail.fields.description.placeholder')"
            :disabled="!editMode && !createMode"
            :label="$t('detail.fields.description.label')"
          ></isard-input-text>

          <isard-input-text
            id="uuid"
            v-model="entity.uuid"
            type="text"
            placeholder="UUID"
            :disabled="!editMode && !createMode"
            class="p-error"
            label="UUID"
          ></isard-input-text>
        </div>
      </div>
      <br />

      <div v-if="!createMode" class="card">
        <h4>Users</h4>
        <div class="p-grid p-formgrid">
          <DataTable :value="entity.users">
            <Column
              field="name"
              :header="$t('detail.fields.name.label')"
            ></Column>
            <Column
              field="surname"
              :header="$t('detail.fields.surname.label')"
            ></Column>
            <Column field="uuid" header="UUID"></Column>
          </DataTable>
        </div>
      </div>
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
import EntitiesUtils from '@/utils/EntitiesUtils';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import IsardInputText from '@/components/shared/forms/IsardInputText.vue';
import MainFormButtonsVue from '@/components/shared/forms/MainFormButtons.vue';

export default defineComponent({
  components: {
    MainFormButtons: MainFormButtonsVue,
    IsardInputText: IsardInputText,
    DataTable: DataTable,
    Column: Column
  },
  setup() {
    const store = useStore();
    const entityImage = EntitiesUtils.detailCleaner(
      cloneDeep(store.getters.detail)
    );
    const entity = reactive(cloneDeep(entityImage));

    const editMode: ComputedRef<any> = computed(() => store.getters.editMode);
    const createMode: ComputedRef<any> = computed(
      () => store.getters.createMode
    );
    const editEnabled = true;

    const formChanged: ComputedRef<boolean> = computed(
      () => JSON.stringify(entity) !== JSON.stringify(entityImage)
    );

    function f_saveItem(): void {
      let persistenceObject = UpdateUtils.getUpdateObject(
        cloneDeep(entity),
        cloneDeep(entityImage)
      );

      persistenceObject.id = entity.id;

      const payload = { persistenceObject };
      store.dispatch(ActionTypes.SAVE_ITEM, payload);
    }

    function f_saveNewItem(): void {
      const persistenceObject = UpdateUtils.getUpdateObject(
        cloneDeep(entity),
        cloneDeep(store.getters.detail)
      );

      const payload = { persistenceObject };
      store.dispatch(ActionTypes.SAVE_NEW_ITEM, payload);
    }

    return {
      entity,
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
