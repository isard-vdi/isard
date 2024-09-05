<template>
  <div>
    <b-row>
      <b-col
        cols="12"
        xl="12"
      >
        <b-alert
          show
          variant="danger"
        >
          <span v-if="isOwner">
            <b-icon
              class="mr-2"
              icon="exclamation-triangle-fill"
            />
            {{ $t(`views.deployment.modal.body.co-owners-warning`) }}
          </span>
          <span v-else>
            <b-icon
              class="mr-2"
              icon="exclamation-triangle-fill"
            />
            {{ $t(`views.deployment.modal.body.warning-co-owner`) }}
          </span>
        </b-alert>
        <hr>
      </b-col>
    </b-row>
    <b-row>
      <b-col
        cols="12"
        xl="12"
        class="ml-2 mb-2"
      >
        {{ $t('views.deployment.modal.body.owner-label', {owner: owner}) }}
      </b-col>
    </b-row>
    <b-row>
      <b-col
        cols="12"
        xl="12"
      >
        <label
          for="coOwnersField"
          class="ml-2 mb-0"
        >
          {{ $t('views.deployment.modal.body.co-owners-label') }}
        </label>
      </b-col>
    </b-row>
    <b-row>
      <b-col
        cols="12"
        xl="12"
      >
        <AllowedSelect
          id="coOwnersField"
          :placeholder="$t('forms.allowed.placeholder')"
          :disabled="!isOwner"
          :table="'users'"
          :options="coOwners"
          :selected-values="selectedCoOwners"
          :roles="['user']"
        />
      </b-col>
    </b-row>
  </div>
</template>
<script>
import { computed } from '@vue/composition-api'
import AllowedSelect from '@/components/AllowedSelect.vue'

export default {
  components: {
    AllowedSelect
  },
  setup (props, context) {
    const $store = context.root.$store

    const isOwner = computed(() => $store.getters.getUser.user_id === $store.getters.getCoOwners.owner.id)

    const owner = computed(() => $store.getters.getCoOwners.owner.label)
    const coOwners = computed(() => $store.getters.getUsers)

    const selectedCoOwners = computed(() => $store.getters.getSelectedUsers)

    return {
      isOwner,
      owner,
      coOwners,
      selectedCoOwners
    }
  }
}
</script>
