<template>
  <div class="p-grid p-fluid">
    <div class="p-col-12 p-md-12">
      <div class="card">
        <h2>{{ $t('detail.headers.user') }}</h2>
        <div class="p-grid p-formgrid">
          <isard-input-text
            id="userid"
            v-model="user.id"
            type="text"
            :placeholder="$t('detail.fields.id.placeholder')"
            :label="$t('detail.fields.id.label')"
            :disabled="true"
            colspan="4"
          ></isard-input-text>

          <isard-input-text
            id="username"
            v-model="user.name"
            v-tooltip="'Enter your username'"
            type="text"
            :placeholder="$t('detail.fields.name.placeholder')"
            :disabled="!editMode"
            :label="$t('detail.fields.name.label')"
            colspan="4"
          ></isard-input-text>

          <isard-input-text
            id="usersurname"
            v-model="user.surname"
            type="text"
            :placeholder="$t('detail.fields.surname.placeholder')"
            :disabled="!editMode"
            class="p-error"
            :label="$t('detail.fields.surname.label')"
            colspan="4"
          ></isard-input-text>
        </div>
        <!-- end grid -->
      </div>
      <!-- end card -->

      <br />

      <div v-if="!createMode" class="card">
        <h4>Entities</h4>
        <div class="p-grid p-formgrid">
          <DataTable :value="user.entities">
            <Column
              field="description"
              :header="$t('detail.fields.description.label')"
            ></Column>
            <Column
              field="name"
              :header="$t('detail.fields.name.label')"
            ></Column>
            <Column field="uuid" header="UUID"></Column>
          </DataTable>
        </div>
      </div>
      <main-form-buttons
        :edit-enabled="editEnabled"
        :form-changed="formChanged"
        @savebuttonPressed="saveItem"
      />
    </div>
    <!-- end cols -->
  </div>
  <!-- end base grid -->
</template>

<script lang="ts">
import { useStore } from '@/store';
import { ActionTypes } from '@/store/actions';
import UpdateUtils from '@/utils/UpdateUtils';
import { cloneDeep } from 'lodash';
import { computed, ComputedRef, defineComponent, reactive } from 'vue';
import MainFormButtons from '@/components/shared/forms/MainFormButtons.vue';
import UsersUtils from '@/utils/UsersUtils';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import IsardInputText from '@/components/shared/forms/IsardInputText.vue';

export default defineComponent({
  components: {
    MainFormButtons: MainFormButtons,
    IsardInputText: IsardInputText,
    DataTable: DataTable,
    Column: Column
  },
  setup() {
    const store = useStore();
    const editEnabled = true;
    const editMode: ComputedRef<any> = computed(() => store.getters.editMode);
    const user = reactive(
      UsersUtils.detailCleaner(cloneDeep(store.getters.detail))
    );
    const userStatic = UsersUtils.detailCleaner(
      cloneDeep(store.getters.detail)
    );

    const formChanged: ComputedRef<boolean> = computed(
      () => JSON.stringify(user) !== JSON.stringify(store.getters.detail)
    );

    function saveItem(): void {
      let persistenceObject = UpdateUtils.getUpdateObject(
        cloneDeep(user),
        userStatic
      );

      persistenceObject.id = user.id;

      const payload = { persistenceObject: persistenceObject };
      store.dispatch(ActionTypes.SAVE_ITEM, payload);
    }

    return {
      user,
      formChanged,
      editEnabled,
      editMode,
      saveItem
    };
  },
  data() {
    return {
      // user: store.getters.detail
    };
  }
});
</script>
