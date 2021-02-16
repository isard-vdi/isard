<template>
  <div class="p-d-flex p-flex-column">
    <div>searchbar <button @click="actionFilterSearch">Filter</button></div>
    <div>
      <DataTable :value="itemsList">
        <Column field="name" header="Name"></Column>
        <Column field="surname1" header="Surname"></Column>
        <Column field="userName" header="Username"></Column>
        <Column field="profile" header="Profile"></Column>
      </DataTable>
    </div>
    <div>pagination component</div>
  </div>
</template>

<script lang="ts">
import { computed, defineComponent, ref } from 'vue';
import { useStore } from '../../store';
import { ActionTypes } from '@/store/actions';
import { MutationTypes } from '../../store/mutations';

export default defineComponent({
  setup(props, context) {
    const store = useStore();

    const increment = () => {
      store.commit(MutationTypes.INC_COUNTER, 3);
    };

    const doubleCounter = computed(() => store.getters.doubleCounter);

    const actionIncrement = () => {
      store.dispatch(ActionTypes.INC_COUNTER, 2);
    };

    const itemsList = computed(() => store.getters.searchResults);
    const actionFilterSearch = () => {
      store.dispatch(ActionTypes.DO_SEARCH, {
        section: '',
        query: '',
        queryParams: []
      });
    };

    return {
      increment,
      doubleCounter,
      actionIncrement,
      actionFilterSearch,
      itemsList
    };
  },
  data() {
    return {};
  }
});
</script>
