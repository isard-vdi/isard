<template>
  <div
    class="d-flex flex-column justify-content-center align-items-center"
  >
    <b-row
      :cols="userCategories.length > MAX_CATEGORIES_GRID ? 2 : 1"
      class="p-2"
    >
      <b-col
        v-for="cat in userCategories"
        :key="cat.id"
        class="p-2"
      >
        <b-button
          class="d-flex flex-column justify-content-center align-items-start text-left w-100"
          variant="outline-secondary"
          @click="loginWithCategory(cat.id)"
        >
          <small
            v-b-tooltip="{ title: `${cat.name.length > MAX_DESCRIPTION_SIZE ? cat.name : ''}`, placement: 'bottom', customClass: 'isard-tooltip', trigger: 'hover' }"
            :class="userCategories.length > MAX_CATEGORIES_GRID ? 'two-line-truncate' : 'one-line-truncate'"
          >
            {{ cat.name }}
          </small>
        </b-button>
      </b-col>
    </b-row>
    <span class="mt-2 d-flex flex-row justify-content-between w-100 px-2 text-left">
      {{ $t('views.select-category.subtitle', {user: getUser.name}) }}
      <b
        class="cursor-pointer text-right"
        @click="logout()"
      >
        {{ $t('views.select-category.logout') }}
      </b>
    </span>
  </div>
</template>

<script>
import { computed } from '@vue/composition-api'
import { mapGetters } from 'vuex'

export default {
  name: 'SelectCategory',
  setup (props, context) {
    const $store = context.root.$store

    const MAX_DESCRIPTION_SIZE = 75
    const MAX_CATEGORIES_GRID = 5 // DEFAULT: 5

    const userCategories = computed(() => $store.getters.getUserCategories)

    $store.dispatch('fetchUserCategories')

    const loginWithCategory = (category) => {
      $store.dispatch('selectCategory', category)
    }

    const logout = () => {
      $store.dispatch('logout')
    }

    return {
      MAX_DESCRIPTION_SIZE,
      MAX_CATEGORIES_GRID,
      userCategories,
      loginWithCategory,
      logout
    }
  },
  computed: {
    ...mapGetters([
      'getUser'
    ])
  }
}
</script>

<style scoped>
  .two-line-truncate {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.2rem !important;
    height: 2.4rem !important;
  }

  .one-line-truncate {
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
