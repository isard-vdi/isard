<template>
  <b-modal
    id="showDirectLinkModal"
    v-model="showDirectLinkModal"
    size="lg"
    :title="$t(`forms.direct-link.modal.title`)"
    centered
    @hidden="closeDirectLinkModal"
  >
    <b-row class="ml-2 mr-2">
      <b-col cols="12">
        <b-form-checkbox
          id="linkEnabled"
          v-model="linkEnabled"
          name="linkEnabled"
          :value="true"
          :unchecked-value="false"
        >
          {{ $t('forms.direct-link.modal.enable') }}
        </b-form-checkbox>
      </b-col>
    </b-row>
    <b-row
      v-if="directLink"
      class="ml-2 mr-2"
    >
      <b-col cols="12">
        <b-input-group
          class="mt-3"
          title="Copy to clipboard"
          @click="copyLink()"
        >
          <template #append>
            <b-input-group-text
              v-b-tooltip.hover
              class="cursor-pointer"
            >
              <b-icon
                icon="clipboard"
                aria-hidden="true"
                class="text-medium-gray mr-2 mr-lg-0"
              />
            </b-input-group-text>
          </template>
          <b-form-input
            id="directLink"
            v-model="directLink"
            v-b-tooltip.hover
            type="text"
            class="cursor-pointer"
            readonly
          />
        </b-input-group>
      </b-col>
    </b-row>
    <template #modal-footer>
      <div class="w-100">
        <b-button
          class="float-right"
          @click="closeDirectLinkModal"
        >
          {{ $t('forms.cancel') }}
        </b-button>
      </div>
    </template>
  </b-modal>
</template>
<script>
import { computed, watch } from '@vue/composition-api'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const directLinkDomainId = computed(() => $store.getters.getDirectLinkDomainId)

    const linkEnabled = computed({
      get: () => $store.getters.getDirectLinkEnabled,
      set: (value) => $store.commit('setDirectLinkEnabled', value)
    })

    const directLink = computed({
      get: () => $store.getters.getDirectLink,
      set: (value) => $store.commit('setDirectLink', value)
    })

    watch(linkEnabled, (newVal, prevVal) => {
      if (prevVal !== null && newVal !== null) {
        $store.dispatch('toggleDirectLink', { disabled: !newVal, domainId: directLinkDomainId.value })
      }
    })

    const showDirectLinkModal = computed({
      get: () => $store.getters.getDirectLinkModalShow,
      set: (value) => $store.commit('setDirectLinkModalShow', value)
    })

    const closeDirectLinkModal = () => {
      $store.dispatch('resetDirectLinkState')
      $store.dispatch('directLinkModalShow', false)
    }

    const copyLink = () => {
      document.querySelector('#directLink').select()
      document.execCommand('copy')
    }

    return { directLink, showDirectLinkModal, closeDirectLinkModal, copyLink, linkEnabled }
  }
}
</script>
