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
            label="Name"
            colspan="4"
          ></isard-input-text>

          <isard-input-text
            id="usersurname"
            v-model="user.surname"
            type="text"
            placeholder="Surnamne"
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
            label="Name"
            colspan="4"
          ></isard-input-text>

          <isard-input-text
            id="entityuuid"
            v-model="user.entity.uuid"
            type="text"
            placeholder="uiid"
            class="p-error"
            label="uiid"
            colspan="4"
          ></isard-input-text>
        </div>
        <!-- end grid -->
      </div>
      <!-- end card -->
      <div class="p-grid p-jc-end p-m-2">
        <!-- buttons -->
        <isard-button v-if="editMode" label="Cancel" />
        <isard-button v-if="editMode" label="Save" />
        <isard-button v-if="!editMode" label="Edit" @click="goToEditMode" />
      </div>
      <!-- end buttons -->
    </div>
    <!-- end cols -->
  </div>
  <!-- end base grid -->
</template>

<script lang="ts">
import { store } from '@/store';
import { ActionTypes } from '@/store/actions';
import { computed, defineComponent } from 'vue';
import IsardButton from '../shared/forms/IsardButton.vue';

export default defineComponent({
  components: { IsardButton },
  setup() {
    const editMode = computed(() => store.getters.editMode);

    function goToEditMode() {
      console.log('goToEditMode');
      store.dispatch(ActionTypes.ACTIVATE_EDIT_MODE);
    }

    return {
      editMode,
      goToEditMode
    };
  },
  data() {
    return {
      user: store.getters.detailForUpdate
    };
  }
});
</script>
