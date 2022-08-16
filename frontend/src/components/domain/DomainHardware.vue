<template>
  <div>
    <!-- Title -->
    <h4 class="my-4">
      <strong>{{ $t('forms.domain.hardware.title') }}</strong>
    </h4>
    <!-- Domain changed data -->
    <p
      v-if="domain.limitedHardware"
      class="text-danger font-weight-bold"
    >
      <b-icon
        class="mr-2"
        variant="danger"
        icon="exclamation-triangle-fill"
      />
      {{ $t('forms.domain.hardware.warning') }}
      <b-row>
        <b-col
          v-for="[key, value] of Object.entries(domain.limitedHardware)"
          :key="key"
          cols="12"
          xl="2"
        >
          <ul>
            {{ hardwareWarningTitle[key] }}
            <li v-if="['videos', 'boot_order', 'isos', 'vgpus', 'floppies'].includes(key)">
              <span
                v-for="change of value['old_value']"
                :key="change['id']"
              >
                {{ change['name'] }}
              </span>
              <b-icon
                v-if="Array.isArray(value['new_value']) && value['new_value'].length > 0"
                icon="arrow-right"
              />
              <span
                v-for="change of value['new_value']"
                :key="change['id']"
              >
                {{ change['name'] }}
              </span>
            </li>
            <li v-else>
              <span>
                {{ value['old_value'] }}
              </span>
              <b-icon
                icon="arrow-right"
              />
              <span>
                {{ value['new_value'] }}
              </span>
            </li>
          </ul>
        </b-col>
      </b-row>
    </p>
    <!-- Boots -->
    <b-row>
      <b-col
        cols="12"
        xl="4"
      >
        {{ $t(`forms.domain.hardware.vcpus`) }}
        <v-select
          v-model="vcpus"
          :options="availableHardware.vcpus"
          label="name"
        />
      </b-col>
      <b-col
        cols="12"
        xl="4"
      >
        {{ $t(`forms.domain.hardware.memory`) }}
        <v-select
          v-model="memory"
          :options="availableHardware.memory"
          label="name"
        />
      </b-col>
      <b-col
        cols="12"
        xl="4"
      >
        {{ $t(`forms.domain.hardware.graphics`) }}
        <v-select
          v-model="graphics"
          :options="availableHardware.graphics"
          label="name"
          :reduce="element => element.id"
        />
      </b-col>
      <b-col
        cols="12"
        xl="4"
      >
        {{ $t(`forms.domain.hardware.videos`) }}
        <v-select
          v-model="videos"
          :options="availableHardware.videos"
          label="name"
          :reduce="element => element.id"
        />
      </b-col>
      <b-col
        cols="12"
        xl="4"
      >
        {{ $t(`forms.domain.hardware.boot`) }}
        <v-select
          v-model="bootOrder"
          :options="availableHardware.bootOrder"
          label="name"
          :reduce="element => element.id"
        />
      </b-col>
      <b-col
        cols="12"
        xl="4"
      >
        {{ $t(`forms.domain.hardware.disk-bus`) }}
        <v-select
          v-model="diskBus"
          :options="availableHardware.diskBus"
          label="name"
          :reduce="element => element.id"
        />
      </b-col>
      <b-col
        cols="12"
        xl="12"
      >
        {{ $t(`forms.domain.hardware.interfaces`) }}
        <v-select
          v-model="interfaces"
          :options="availableHardware.interfaces"
          label="name"
          :close-on-select="false"
          :multiple="true"
          :reduce="element => element.id"
        />
      </b-col>
    </b-row>
  </div>
</template>

<script>
import { computed, onMounted } from '@vue/composition-api'
import { hardwareWarningTitle } from '@/shared/constants'

export default {
  setup (props, context) {
    const $store = context.root.$store
    const domain = computed(() => $store.getters.getDomain)
    const availableHardware = computed(() => $store.getters.getHardware)
    const vcpus = computed({
      get: () => $store.getters.getDomain.hardware.vcpus,
      set: (value) => {
        domain.value.hardware.vcpus = value
        $store.commit('setDomain', domain.value)
      }
    })
    const memory = computed({
      get: () => $store.getters.getDomain.hardware.memory,
      set: (value) => {
        domain.value.hardware.memory = value
        $store.commit('setDomain', domain.value)
      }
    })
    const graphics = computed({
      get: () => $store.getters.getDomain.hardware.graphics,
      set: (value) => {
        domain.value.hardware.graphics = [value]
        $store.commit('setDomain', domain.value)
      }
    })
    const videos = computed({
      get: () => $store.getters.getDomain.hardware.videos,
      set: (value) => {
        domain.value.hardware.videos = [value]
        $store.commit('setDomain', domain.value)
      }
    })
    const bootOrder = computed({
      get: () => $store.getters.getDomain.hardware.bootOrder,
      set: (value) => {
        domain.value.hardware.bootOrder = [value]
        $store.commit('setDomain', domain.value)
      }
    })
    const diskBus = computed({
      get: () => $store.getters.getDomain.hardware.diskBus,
      set: (value) => {
        domain.value.hardware.diskBus = value
        $store.commit('setDomain', domain.value)
      }
    })
    const interfaces = computed({
      get: () => $store.getters.getDomain.hardware.interfaces,
      set: (value) => {
        domain.value.hardware.interfaces = value
        $store.commit('setDomain', domain.value)
      }
    })
    onMounted(() => {
      $store.dispatch('fetchHardware')
    })
    return {
      vcpus,
      memory,
      graphics,
      videos,
      bootOrder,
      diskBus,
      interfaces,
      availableHardware,
      domain,
      hardwareWarningTitle
    }
  }
}
</script>
