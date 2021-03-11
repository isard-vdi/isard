<template>
  <div class="p-grid p-fluid">
    <div class="p-col-12 p-md-12">
      <div class="card">
        <h2>User Detail</h2>
        <div class="p-grid p-formgrid">
          <div class="p-col-12 p-mb-2 p-lg-4 p-mb-lg-0">
            <label for="entityid">ID</label>
            <InputText
              id="entityid"
              v-model="entity.id"
              type="text"
              placeholder="ID"
              :disabled="true"
            ></InputText>
          </div>
          <div class="p-col-12 p-mb-2 p-lg-4 p-mb-lg-0">
            <label for="entityname">Name</label>
            <InputText
              id="entityname"
              v-model="entity.name"
              type="text"
              placeholder="Name"
            ></InputText>
          </div>

          <div class="p-col-12 p-mb-2 p-lg-4 p-mb-lg-0">
            <label for="entityuuid">UUID</label>
            <InputText
              id="entityuuid"
              v-model="entity.uuid"
              type="text"
              placeholder="UUID"
              class="p-error"
            />
          </div>
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

export default defineComponent({
  setup() {},
  data() {
    return {
      entity: store.getters.detailForUpdate
    };
  }
});
</script>
