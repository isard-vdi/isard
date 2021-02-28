<template>
  <div class="p-d-flex p-flex-column">
    <div><button @click="actionIncrement">Search</button></div>
    <div>
      Double
      <h3>{{ doubleCounter }}</h3>
    </div>
    <div>searchbar <button @click="actionFilterSearch">Filter</button></div>
    <div>
      <DataTable :value="usersList">
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
import { computed, defineComponent, ref } from 'vue';
import { useStore } from '../store';
import { ActionTypes } from '@/store/actions';
import { DEFAULT_SEARCH_SIZE } from '@/config/constants';

export default defineComponent({
  setup(props, context) {
    const store = useStore();

    const usersList = computed(() => store.getters.searchResults);
    const actionFilterSearch = () => {
      store.dispatch(ActionTypes.DO_SEARCH, {
        query: '',
        queryParams: [],
        size: DEFAULT_SEARCH_SIZE,
        start: 0
      });
    };

    return {
      actionFilterSearch,
      usersList
    };
  },
  data() {
    return {};
  }
});
</script>
