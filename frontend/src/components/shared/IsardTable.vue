<template>
  <div class="table-list">
    <b-skeleton-wrapper
      :loading="loading"
      class="pb-1 pt-4 justify-content-start"
    >
      <template #loading>
        <b-col>
          <list-item-skeleton class="mb-2" />
          <list-item-skeleton class="mb-2" />
          <list-item-skeleton class="mb-2" />
          <list-item-skeleton class="mb-2" />
        </b-col>
      </template>
      <!-- Filter -->
      <b-row class="mt-2">
        <b-col
          cols="8"
          md="6"
          lg="4"
          xl="4"
        >
          <b-input-group size="sm">
            <b-form-input
              id="filter-input"
              v-model="filter"
              type="search"
              :placeholder="$t('forms.filter-placeholder')"
            />
            <b-input-group-append>
              <b-button
                :disabled="!filter"
                @click="filter = ''"
              >
                {{ $t('forms.clear') }}
              </b-button>
            </b-input-group-append>
          </b-input-group>
        </b-col>
        <b-row
          class="ml-auto mr-2"
        >
          <b-col>
            <b-form-group
              :label="$t('forms.show-pages')"
              label-for="per-page-select"
              label-cols-md="5"
              label-align-sm="right"
              class="text-medium-gray mr-2 mr-lg-0"
            >
              <b-form-select
                id="per-page-select"
                v-model="perPage"
                :label="$t('forms.show-pages')"
                :options="pageOptions"
                size="sm"
              />
            </b-form-group>
          </b-col>
          <b-col>
            <b-pagination
              v-model="currentPage"
              :total-rows="totalRows"
              :per-page="perPage"
              aria-controls="isardTable-table"
              size="sm"
            />
          </b-col>
        </b-row>
      </b-row>
      <b-row>
        <b-col
          cols="12"
          class="d-flex flex-row flex-wrap justify-content-start"
        >
          <b-table
            id="isardTable-table"
            :items="items"
            :fields="fields"
            :responsive="true"
            :per-page="perPage"
            :current-page="currentPage"
            :filter="filter"
            :filter-included-fields="filterOn"
            :tbody-tr-class="rowClass"
            @filtered="onFiltered"
            @row-clicked="onClickRow"
          >
            <slot
              v-for="slot in Object.keys($slots)"
              :slot="slot"
              :name="slot"
            />
            <template
              v-for="slot in Object.keys($scopedSlots)"
              :slot="slot"
              slot-scope="scope"
            >
              <slot
                :name="slot"
                v-bind="scope"
              />
            </template>
          </b-table>
          <b-row
            class="ml-auto mr-2"
          >
            <b-col>
              <b-form-group
                :label="$t('forms.show-pages')"
                label-for="per-page-select"
                label-cols-md="5"
                label-align-sm="right"
                class="text-medium-gray mr-2 mr-lg-0"
              >
                <b-form-select
                  id="per-page-select"
                  v-model="perPage"
                  :label="$t('forms.show-pages')"
                  :options="pageOptions"
                  size="sm"
                />
              </b-form-group>
            </b-col>
            <b-col>
              <b-pagination
                v-model="currentPage"
                :total-rows="totalRows"
                :per-page="perPage"
                aria-controls="isardTable-table"
                size="sm"
              />
            </b-col>
          </b-row>
        </b-col>
      </b-row>
    </b-skeleton-wrapper>
  </div>
</template>

<script>
import ListItemSkeleton from '@/components/ListItemSkeleton.vue'
import { ref, watch } from '@vue/composition-api'

export default {
  components: {
    ListItemSkeleton
  },
  props: {
    items: {
      required: true,
      type: Array
    },
    loading: {
      required: true,
      type: Boolean
    },
    pageOptions: {
      required: true,
      type: Array
    },
    defaultPerPage: {
      required: false,
      type: Number,
      default: 10
    },
    filterOn: {
      required: true,
      type: Array
    },
    fields: {
      required: true,
      type: Array
    },
    rowClass: {
      required: false,
      default: '',
      type: [String, Function]
    }
  },
  setup (props, context) {
    const perPage = ref(props.defaultPerPage)
    const currentPage = ref(1)
    const totalRows = ref(1)
    const filter = ref('')

    const onFiltered = (filteredItems) => {
      // Trigger pagination to update the number of buttons/pages due to filtering
      totalRows.value = filteredItems.length
      currentPage.value = 1
    }

    const onClickRow = (event, e) => {
      context.emit('rowClicked', event)
    }

    watch(() => props.items, (newVal, prevVal) => {
      totalRows.value = newVal.length
    }, { immediate: true })

    return {
      onFiltered,
      filter,
      currentPage,
      totalRows,
      perPage,
      onClickRow
    }
  }
}

</script>
