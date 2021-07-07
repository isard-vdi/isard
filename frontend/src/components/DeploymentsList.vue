<template>
  <div class='table-list px-5'>
    <b-container fluid class='px-0'>
      <b-skeleton-wrapper :loading="loading" class='pb-1 pt-4 justify-content-start'>
              <template #loading>
                <b-col>
                  <list-item-skeleton class="mb-2"></list-item-skeleton>
                  <list-item-skeleton class="mb-2"></list-item-skeleton>
                  <list-item-skeleton class="mb-2"></list-item-skeleton>
                </b-col>
              </template>
      <b-row>
        <b-col
          cols='12'
          class='py-3 p-5 pt-4 d-flex flex-row flex-wrap justify-content-start'
        >
          <b-table :items='deployments' :fields='fields' @row-clicked="redirectDeployment" tbody-tr-class="cursor-pointer">
            <template #cell(name)='data'>
              <p class='m-0 font-weight-bold'>
                {{ data.item.name }}
              </p>
            </template>
            <template #cell(description)='data'>
              <p class='text-dark-gray m-0'>
                {{ data.item.description }}
              </p>
            </template>
            <template #cell(currentlyUsedDesktops)='data'>
              <p class='text-dark-gray m-0'>
                {{ data.item.currentlyUsedDesktops }} / {{ data.item.totalDesktops }}
              </p>
            </template>
          </b-table>
          </b-col>
      </b-row>
      </b-skeleton-wrapper>
    </b-container>
  </div>
</template>
<script>
// import i18n from '@/i18n'
import ListItemSkeleton from '@/components/ListItemSkeleton.vue'

export default {
  components: { ListItemSkeleton },
  props: {
    deployments: {
      required: true,
      type: Array
    },
    loading: {
      required: true,
      type: Boolean
    }
  },
  methods: {
    redirectDeployment (item) {
      this.$router.push({ name: 'Deployment', params: { id: item.id } })
    }
  },
  data () {
    return {
      fields: [
        {
          key: 'name',
          sortable: true,
          label: 'Nombre',
          thStyle: { width: '25%' },
          tdClass: 'name'
        },
        {
          key: 'startedDesktops',
          sortable: true,
          label: 'Escritorios en uso',
          thStyle: { width: '35%' }
        }
      ]
    }
  }
}
</script>
