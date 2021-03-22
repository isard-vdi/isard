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
      <main-form-buttons />
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, reactive } from 'vue';
import { useStore } from '@/store';
import { cloneDeep } from 'lodash';

const store = useStore();

export default defineComponent({
  setup() {
    const entity = reactive(cloneDeep(store.getters.detail));

    return entity;
  },
  data() {
    return {};
  }
});
</script>
