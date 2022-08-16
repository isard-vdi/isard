<template>
  <div>
    <!-- Title -->
    <h4 class="my-4">
      <strong>{{ $t('forms.domain.viewers.title') }}</strong>
    </h4>
    <b-form-group
      v-slot="{ ariaDescribedby }"
    >
      <b-form-checkbox-group
        id="viewers"
        v-model="viewers"
        :aria-describedby="ariaDescribedby"
        name="viewers"
      >
        <b-row class="justify-content-center text-center">
          <b-form-checkbox
            v-for="viewer in orderBy(selectableViewers, 'order')"
            :key="viewer.id"
            :value="{ [viewer.key]: {options: null} }"
          >
            <b-col md="12">
              <div class="bg-white rounded-15 py-4 px-5 my-4 text-center cursor-pointer">
                <div
                  style="height: 5rem; width: 10rem; padding-top: 0.5rem"
                  class="mb-4"
                >
                  <img
                    :src="require(`@/assets/img/icons/${viewer.type}.svg`)"
                    alt=""
                    style="max-inline-size: fit-content;"
                  >
                </div>
                <div>
                  <p>
                    {{ viewer.name }}
                  </p>
                </div>
              </div>
            </b-col>
          </b-form-checkbox>
        </b-row>
      </b-form-checkbox-group>
    </b-form-group>
    <!-- Guest username -->
    <span v-if="wireguard">
      <h4>
        <strong>{{ $t('forms.domain.viewers.guest.title') }}</strong>
      </h4>
      <p class="text-danger font-weight-bold">
        <b-icon
          class="mr-2"
          variant="danger"
          icon="exclamation-triangle-fill"
        />
        {{ $t('forms.domain.viewers.guest.warning') }}
      </p>
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <label for="usernameField">{{ $t('forms.domain.viewers.guest.username') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
        >
          <b-form-input
            id="usernameField"
            v-model="username"
            type="text"
            size="sm"
          />
        </b-col>
      </b-row>

      <!-- Guest password -->
      <b-row class="mt-4">
        <b-col
          cols="4"
          xl="2"
        >
          <label for="passwordField">{{ $t('forms.domain.viewers.guest.password') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
        >
          <b-form-input
            id="passwordField"
            v-model="password"
            type="text"
            size="sm"
          />
        </b-col>
      </b-row>
    </span>
  </div>
</template>

<script>
import { computed, watch } from '@vue/composition-api'
import { availableViewers } from '@/shared/constants'
import { orderBy, flow } from 'lodash'

export default {
  setup (props, context) {
    const $store = context.root.$store
    const domain = computed(() => $store.getters.getDomain)
    const viewers = computed({
      get: () => $store.getters.getDomain.guestProperties.viewers,
      set: (value) => {
        domain.value.guestProperties.viewers = value
        $store.commit('setDomain', domain.value)
      }
    })
    const username = computed({
      get: () => $store.getters.getDomain.guestProperties.credentials.username,
      set: (value) => {
        domain.value.guestProperties.credentials.username = value
        $store.commit('setDomain', domain.value)
      }
    })
    const password = computed({
      get: () => $store.getters.getDomain.guestProperties.credentials.password,
      set: (value) => {
        domain.value.guestProperties.credentials.password = value
        $store.commit('setDomain', domain.value)
      }
    })

    const wireguard = computed(() => domain.value.hardware.interfaces.includes('wireguard'))
    watch(wireguard, (newVal, prevVal) => {
      if (!wireguard.value) {
        $store.dispatch('removeWireguardViewers')
      }
    })
    const selectableViewers = computed(() => wireguard.value
      ? availableViewers
      : flow([
        Object.entries,
        arr => arr.filter(([key, value]) => !value.needsWireguard),
        Object.fromEntries
      ])(availableViewers))

    return {
      viewers,
      selectableViewers,
      username,
      password,
      orderBy,
      wireguard
    }
  }
}
</script>
