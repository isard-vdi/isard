<template>
  <div>
    <!-- Title -->
    <h4 class="my-2">
      <strong>{{ $t('forms.domain.viewers.title') }}</strong>
    </h4>
    <b-row>
      <b-col cols="12">
        <div class="d-flex">
          <label
            for="switch_1"
            class="mr-2"
          ><b-icon
            icon="fullscreen-exit"
            class="mr-2"
            variant="danger"
          />{{ $t('forms.domain.viewers.fullscreen-disabled') }}</label>
          <b-form-checkbox
            v-model="fullscreen"
            switch
          >
            <b-icon
              class="mr-2"
              icon="fullscreen"
              variant="success"
            />{{ $t('forms.domain.viewers.fullscreen-enabled') }}
          </b-form-checkbox>
        </div>
      </b-col>
    </b-row>
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
            v-for="viewer of orderBy(availableViewers, 'order')"
            :key="viewer.id"
            :value="{ [viewer.key]: {options: null} }"
          >
            <b-col md="12">
              <div class="bg-white rounded-15 py-2 px-3 my-2 text-center cursor-pointer">
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
                  <span>
                    {{ $t(`views.select-template.viewer-name.${viewer.type}-${viewer.id}`) }}
                  </span>
                </div>
              </div>
            </b-col>
          </b-form-checkbox>
        </b-row>
      </b-form-checkbox-group>
    </b-form-group>
  </div>
</template>

<script>
import { computed, watch } from '@vue/composition-api'
import { availableViewers } from '@/shared/constants'
import { orderBy } from 'lodash'
import i18n from '@/i18n'
import { ErrorUtils } from '@/utils/errorUtils'

export default {
  setup (props, context) {
    const $store = context.root.$store
    const domain = computed(() => $store.getters.getDomain)
    const fullscreen = computed({
      get: () => $store.getters.getDomain.guestProperties.fullscreen,
      set: (value) => {
        domain.value.guestProperties.fullscreen = value
        $store.commit('setDomain', domain.value)
      }
    })
    const viewers = computed({
      get: () => $store.getters.getDomain.guestProperties.viewers,
      set: (value) => {
        domain.value.guestProperties.viewers = value
        $store.commit('setDomain', domain.value)
      }
    })
    const wireguard = computed(() => domain.value.hardware.interfaces.includes('wireguard'))
    const availableHardware = computed(() => $store.getters.getHardware)
    watch(wireguard, (newVal, prevVal) => {
      if (!wireguard.value) {
        ErrorUtils.showInfoMessage(context.root.$snotify, i18n.t('messages.info.wireguard-viewers-removed'), '', true, 5000)
        $store.dispatch('removeWireguardViewers')
      }
    })

    watch(viewers, (newVal, prevVal) => {
      // Get viewers that require the wireguard network and the currently selected viewers
      const wireguardViewers = availableViewers.filter(viewer => viewer.needsWireguard).map((viewer) => viewer.key)
      const currentViewers = newVal.map((viewer) => Object.keys(viewer)[0])
      // If has selected any wireguard viewer
      if (currentViewers.some(viewer => wireguardViewers.includes(viewer))) {
        context.emit('rdpViewersSelected', true)
        // Add the wireguard network
        if (!wireguard.value) {
          if (availableHardware.value.interfaces.filter(i => i.id === 'wireguard').length) {
            ErrorUtils.showInfoMessage(context.root.$snotify, i18n.t('messages.info.wireguard-network-added'), '', true, 5000)
            domain.value.hardware.interfaces = [...domain.value.hardware.interfaces, 'wireguard']
            $store.commit('setDomain', domain.value)
          } else {
            ErrorUtils.showInfoMessage(context.root.$snotify, i18n.t('messages.info.wireguard-network-required'), '', true, 5000)
            $store.dispatch('removeWireguardViewers')
          }
        }
      } else {
        context.emit('rdpViewersSelected', false)
      }
    })

    return {
      viewers,
      orderBy,
      wireguard,
      fullscreen,
      availableViewers
    }
  }
}
</script>
