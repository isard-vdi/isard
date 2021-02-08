<template>
  <div class="p-d-flex p-flex-column">
    <div>searchbar <button @click="search">Search</button></div>
    <div>
      hola
      <DataTable :value="users">
        <Column field="name" header="Name"></Column>
        <Column field="surname1" header="Surname"></Column>
        <Column field="surname2" header="Surname 2"></Column>
        <Column field="profile" header="Profile"></Column>
      </DataTable>
    </div>
    <div>pagination component</div>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import UserService from '../service/UserService';

const userService = new UserService();

export default defineComponent({
  data() {
    return {
      users: [{ name: 'tony' }]
    };
  },
  methods: {
    search(): void {
      const that = this;

      userService.getUsers().then((response: any): any => {
        console.log(response);
        this.users = response;
      });
    }
  }
});
</script>
