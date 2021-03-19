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
            label="Name"
          ></isard-input-text>

          <isard-input-text
            id="entityuuid"
            v-model="entity.uuid"
            type="text"
            placeholder="UUID"
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
    </div>
  </div>
</template>

<script lang="ts">
import { store } from '@/store';
import { defineComponent } from 'vue';
import Tooltip from 'primevue/tooltip';

export default defineComponent({
  setup() {},
  data() {
    return {
      entity: store.getters.detailForUpdate
    };
  }
});
</script>
