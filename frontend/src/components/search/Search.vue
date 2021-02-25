<template>
  <div class="p-d-flex p-flex-column">
    <div>searchbar <button @click="actionFilterSearch">Filter</button></div>
    <div>
      <DataTable :value="itemsList" class="p-datatable-striped">
        <Column
          v-for="col of sectionConfig.table.columns"
          :key="col.field"
          :field="col.field"
          :header="col.header"
        ></Column>
        <Column :exportable="false">
          <template #body="slotProps">
            <Button
              icon="pi pi-pencil"
              class="p-button-rounded p-button-success p-mr-2"
              @click="f_edit(slotProps.data)"
            />
            <Button
              icon="pi pi-trash"
              class="p-button-rounded p-button-warning"
              @click="f_delete(slotProps.data)"
            />
          </template>
        </Column>
      </DataTable>
    </div>
    <div>pagination component</div>
  </div>
</template>

<script lang="ts">
import { computed, defineComponent, onMounted, ref } from 'vue';
import { useStore } from '../../store';
import { ActionTypes } from '@/store/actions';
import { useRoute } from 'vue-router';
import { sections } from '@/config/sections';
import { SectionConfig } from '@/config/sections-config';
import { DEFAULT_SEARCH_SIZE } from '@/config/constants';

export default defineComponent({
  setup(props, context) {
    const store = useStore();
    const route = useRoute();

    // LifeCycle Hooks
    const section: string = route.name as string;
    const sectionConfig: SectionConfig | null =
      sections[`${section}`].config || null;

    const itemsList = computed(() => store.getters.searchResults);

    const actionFilterSearch = () => {
      store.dispatch(ActionTypes.DO_SEARCH, {
        section: '',
        query: '',
        queryParams: [],
        size: DEFAULT_SEARCH_SIZE,
        start: 0
      });
    };

    const f_delete = (data: any) => {
      console.log(data, 'data');
    };

    return {
      actionFilterSearch,
      itemsList,
      sectionConfig,
      f_delete
    };
  },
  data() {
    return {};
  }
});
</script>
