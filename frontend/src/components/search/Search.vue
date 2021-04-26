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
        <Column
          key="state"
          :style="{ display: showStateColumn ? 'table-cell' : 'none' }"
          column-key="state"
          header="State"
        >
          <template #body="slotProps">
            <span
              :class="
                'product-badge state-' +
                (
                  ((slotProps || {}).data || {}).state || 'default'
                ).toLowerCase()
              "
              >{{ slotProps.data.state }}</span
            >
          </template>
        </Column>
        <Column :exportable="false" header="Actions">
          <template #body="slotProps">
            <Button
              icon="pi pi-pencil"
              class="p-button-rounded p-button-outlined p-mr-2"
              @click="f_edit(slotProps.data)"
            />
            <Button
              icon="pi pi-trash"
              class="p-button-rounded p-button-outlined p-button-warning p-mr-2"
              @click="f_delete(slotProps.data)"
            />
            <Button
              v-if="
                sectionConfig.name === 'desktops' &&
                slotProps.data.state &&
                slotProps.data.state === 'stopped'
              "
              icon="pi pi-caret-right"
              class="p-button-rounded p-button-outlined p-button-success p-mr-2"
              @click="f_start_desktop(slotProps.data)"
            />
            <Button
              v-if="
                sectionConfig.name === 'desktops' &&
                slotProps.data.state &&
                slotProps.data.state === 'started'
              "
              icon="pi pi-power-off"
              class="p-button-rounded p-button-danger p-mr-2"
              @click="console.log('stop')"
            />
            <Button
              v-if="
                sectionConfig.name === 'desktops' &&
                slotProps.data.state &&
                slotProps.data.state === 'started'
              "
              icon="pi pi-eye"
              class="p-button-rounded p-button-danger p-mr-2"
              @click="console.log('view')"
            />
          </template>
        </Column>
      </DataTable>
    </div>
    <div>pagination component</div>
    <ListButtons
      :create-enabled="true"
      @createbuttonPressed="f_create"
    ></ListButtons>
  </div>
</template>

<script lang="ts">
import { computed, ComputedRef, defineComponent, watch } from 'vue';
import { useStore } from '../../store';
import { ActionTypes } from '@/store/actions';
import { sections } from '@/config/sections';
import { SectionConfig } from '@/config/sections-config';
import { DEFAULT_SEARCH_SIZE } from '@/config/constants';
import ListButtons from '@/components/shared/lists/ListButtons.vue';
import Button from 'primevue/button';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import { SectionUsers } from '@/config/section-users';

export default defineComponent({
  components: {
    ListButtons: ListButtons,
    Button: Button,
    DataTable: DataTable,
    Column: Column
  },
  setup(props, context) {
    const store = useStore();

    // LifeCycle Hooks
    const section = computed(() => store.getters.section);
    const sectionAndRoute = computed(
      () => `${store.getters.routeName}:${store.getters.section}`
    );
    const sectionConfig: ComputedRef<SectionConfig> = computed(
      () =>
        (section.value &&
          sections[`${section.value}`] &&
          sections[`${section.value}`].config) ||
        SectionUsers
    );
    const tableExtraColumns = computed(
      () => sectionConfig.value.table.extraColumns || []
    );

    const showStateColumn =
      computed(() => tableExtraColumns.value.indexOf('state') != -1) || false;

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

    const f_start_desktop = (data: any) => {
      store.dispatch(ActionTypes.START_DESKTOP, {
        params: { id: data.uuid }
      });
    };

    return {
      actionFilterSearch,
      itemsList,
      sectionConfig,
      showStateColumn,
      f_edit,
      f_delete,
      f_create,
      f_start_desktop
    };
  }
});
</script>

<style scoped>
.product-badge {
  border-radius: 2px;
  padding: 0.25em 0.5rem;
  text-transform: uppercase;
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.3px;
}

.product-badge.state-stopped {
  background: #feedaf;
  color: #8a5340;
}

.product-badge.state-started {
  background: #c8e6c9;
  color: #256029;
}
</style>
