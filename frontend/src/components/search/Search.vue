<template>
  <div class="p-d-flex p-flex-column">
    <div>searchbar <button @click="actionFilterSearch">Filter</button></div>
    <div>
      <DataTable :value="itemsList" class="p-datatable-striped">
        <Column
          v-for="col of sectionConfig.table?.columns"
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
    <list-buttons
      :create-enabled="true"
      @createbuttonPressed="f_create"
    ></list-buttons>
  </div>
</template>

<script lang="ts">
import { computed, defineComponent, watch } from 'vue';
import { useStore } from '../../store';
import { ActionTypes } from '@/store/actions';
import { sections } from '@/config/sections';
import { SectionConfig } from '@/config/sections-config';
import { DEFAULT_SEARCH_SIZE } from '@/config/constants';
import ListButtons from '@/components/shared/lists/ListButtons.vue';

export default defineComponent({
  components: { ListButtons },
  setup(props, context) {
    const store = useStore();

    // LifeCycle Hooks
    const section = computed(() => store.getters.section);
    const sectionAndRoute = computed(
      () => `${store.getters.routeName}:${store.getters.section}`
    );
    const sectionConfig: SectionConfig | {} = computed(
      () =>
        (section.value &&
          sections[`${section.value}`] &&
          sections[`${section.value}`].config) ||
        {}
    );

    watch(
      sectionAndRoute,
      (sectionAndRoute) => {
        if (sectionAndRoute.split(':')[0] === 'search') {
          store.dispatch(ActionTypes.DO_SEARCH, {
            queryParams: [],
            size: DEFAULT_SEARCH_SIZE,
            start: 0
          });
        }
      },
      {
        immediate: true
      }
    );

    const itemsList = computed(() => store.getters.searchResults);

    const actionFilterSearch = () => {
      store.dispatch(ActionTypes.DO_SEARCH, {
        queryParams: [],
        size: DEFAULT_SEARCH_SIZE,
        start: 0
      });
    };

    const f_edit = (data: any) => {
      store.dispatch(ActionTypes.NAVIGATE_DETAIL, {
        section: section.value,
        params: { id: data.id }
      });
    };

    const f_delete = (user: Types.User) => {
      console.log(user, 'data');
    };

    const f_create = () => {
      store.dispatch(ActionTypes.NAVIGATE_CREATE, {
        section: section.value,
        params: {}
      });
    };

    return {
      actionFilterSearch,
      itemsList,
      sectionConfig,
      f_edit,
      f_delete,
      f_create
    };
  }
});
</script>
