<template>
  <div>
    <!-- Title -->
    <h4 class="my-2">
      <strong>{{ $t('forms.new-deployment.user-permissions.title') }}</strong>
    </h4>

    <b-row
      class="justify-content-center"
    >
      <b-form-checkbox
        v-model="recreate"
        class="my-2 mx-2"
      >
        <div
          class="px-3 py-2 bg-white rounded-15 cursor-pointer"
          style="width: 16rem;"
        >
          <b-icon icon="arrow-counterclockwise" />
          {{ $t('forms.new-deployment.user-permissions.recreate.title') }}
          <br>
          <small>{{ $t('forms.new-deployment.user-permissions.recreate.description') }} </small>
        </div>
      </b-form-checkbox>
    </b-row>
  </div>
</template>

<script>
import { computed, onMounted } from '@vue/composition-api'

export default {
  setup (props, context) {
    const $store = context.root.$store
    const deploymentId = context.root.$route.params.id
    onMounted(() => {
      if (deploymentId) {
        $store.dispatch('fetchPermissions', deploymentId)
      }
    })

    const permissions = computed(() => $store.getters.getPermissions)

    const recreate = computed({
      get: () => permissions.value.includes('recreate'),
      set: (value) => {
        if (value && !permissions.value.includes('recreate')) {
          $store.commit('addPermission', 'recreate')
        } else if (!value) {
          $store.commit('removePermission', 'recreate')
        }
      }
    })

    return {
      recreate
    }
  }
}
</script>
