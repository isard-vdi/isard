<template>
  <div class="p-grid p-fluid">
    <div class="p-col-12 p-md-12">
      <div class="card">
        <h2>User Detail</h2>
        <div class="p-grid p-formgrid">
          <isard-input-text
            id="userid"
            v-model="user.id"
            type="text"
            placeholder="ID"
            label="ID"
            :disabled="true"
            colspan="4"
          ></isard-input-text>

          <isard-input-text
            id="username"
            v-model="user.name"
            v-tooltip="'Enter your username'"
            type="text"
            placeholder="Name"
            :disabled="!editMode"
            label="Name"
            colspan="4"
          ></isard-input-text>

          <isard-input-text
            id="usersurname"
            v-model="user.surname"
            type="text"
            placeholder="Surnamne"
            :disabled="!editMode"
            class="p-error"
            label="Surname"
            colspan="4"
          ></isard-input-text>
        </div>
        <!-- end grid -->
      </div>
      <!-- end card -->
      <br />
      <h4>Entity</h4>
      <div class="card">
        <div class="p-grid p-formgrid">
          <isard-input-text
            id="userentityid"
            v-model="user.entity.id"
            type="text"
            placeholder="ID"
            :disabled="true"
            label="ID"
            colspan="4"
          ></isard-input-text>

          <isard-input-text
            id="entityName"
            v-model="user.entity.name"
            type="text"
            placeholder="Name"
            :disabled="!editMode"
            label="Name"
            colspan="4"
          ></isard-input-text>

          <isard-input-text
            id="entityuuid"
            v-model="user.entity.uuid"
            type="text"
            placeholder="uiid"
            :disabled="!editMode"
            class="p-error"
            label="uiid"
            colspan="4"
          ></isard-input-text>
        </div>
        <!-- end grid -->
      </div>
      <!-- end card -->
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

export default defineComponent({
  components: { MainFormButtons },
  setup() {
    const store = useStore();
    const editEnabled = true;
    const editMode: ComputedRef<any> = computed(() => store.getters.editMode);
    const user = reactive(cloneDeep(store.getters.detail));

    const formChanged: ComputedRef<boolean> = computed(
      () => JSON.stringify(user) !== JSON.stringify(store.getters.detail)
    );

    function saveItem(): void {
      let persistenceObject = UpdateUtils.getUpdateObject(
        cloneDeep(user),
        cloneDeep(store.getters.detail)
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
