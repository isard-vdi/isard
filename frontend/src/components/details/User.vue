<template>
  <div class="p-grid p-fluid">
    <div class="p-col-12 p-md-12">
      <div class="card">
        <h2>User Detail</h2>
        <div class="p-grid p-formgrid">
          <div class="p-col-12 p-mb-2 p-lg-4 p-mb-lg-0">
            <label for="userid">ID</label>
            <InputText
              id="userid"
              v-model="user.id"
              type="text"
              placeholder="ID"
              :disabled="true"
            ></InputText>
          </div>
          <div class="p-col-12 p-mb-2 p-lg-4 p-mb-lg-0">
            <label for="username">Name</label>
            <InputText
              id="username"
              v-model="user.name"
              type="text"
              placeholder="Name"
            ></InputText>
          </div>

          <div class="p-col-12 p-mb-2 p-lg-4 p-mb-lg-0">
            <label for="usersurname">Surname</label>
            <InputText
              id="usersurname"
              v-model="user.surname"
              type="text"
              placeholder="Surnamne"
              class="p-error"
            />
          </div>
        </div>
      </div>
      <br />
      <h4>Entity</h4>
      <div class="card">
        <div class="p-grid p-formgrid">
          <div class="p-col-12 p-mb-2 p-lg-4 p-mb-lg-0">
            <label for="userentityid">ID</label>
            <InputText
              id="userentityid"
              v-model="user.entity.id"
              type="text"
              placeholder="ID"
              :disabled="true"
            ></InputText>
          </div>
          <div class="p-col-12 p-mb-2 p-lg-4 p-mb-lg-0">
            <label for="entityName">Name</label>
            <InputText
              id="entityName"
              v-model="user.entity.name"
              type="text"
              placeholder="Name"
            ></InputText>
          </div>

          <div class="p-col-12 p-mb-2 p-lg-4 p-mb-lg-0">
            <label for="entityuuid">UUID</label>
            <InputText
              id="entityuuid"
              v-model="user.entity.uuid"
              type="text"
              placeholder="uiid"
              class="p-error"
            />
          </div>
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
      user: store.getters.detailForUpdate
    };
  }
});
</script>
