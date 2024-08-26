<template>
  <div>
    <!-- Title -->
    <h4 class="my-2">
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
            <li v-if="['videos', 'boot_order', 'isos', 'vgpus', 'floppies', 'interfaces'].includes(key)">
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
    <!-- vCPUS -->
    <b-row>
      <b-col
        cols="12"
        xl="2"
        class="mb-2"
      >
        {{ $t(`forms.domain.hardware.vcpus`) }}
        <v-select
          v-model="vcpus"
          :options="availableHardware.vcpus"
          label="name"
          @search:blur="v$.vcpus.$touch"
        >
          <template #search="{ attributes, events }">
            <input
              id="vcpus"
              class="vs__search"
              v-bind="attributes"
              v-on="events"
            >
          </template>
        </v-select>
        <div
          v-if="v$.vcpus.$error"
          id="vcpusError"
          class="text-danger"
        >
          {{ $t(`validations.${v$.vcpus.$errors[0].$validator}`, { property: `${$t("forms.domain.hardware.vcpus")}` }) }}
        </div>
      </b-col>
      <!-- Memory -->
      <b-col
        cols="12"
        xl="2"
        class="mb-2"
      >
        {{ $t(`forms.domain.hardware.memory`) }}
        <v-select
          v-model="memory"
          :options="availableHardware.memory"
          label="name"
          @search:blur="v$.memory.$touch"
        >
          <template #search="{ attributes, events }">
            <input
              id="memory"
              class="vs__search"
              v-bind="attributes"
              v-on="events"
            >
          </template>
        </v-select>
        <div
          v-if="v$.memory.$error"
          id="memoryError"
          class="text-danger"
        >
          {{ $t(`validations.${v$.memory.$errors[0].$validator}`, { property: `${$t("forms.domain.hardware.memory")}` }) }}
        </div>
      </b-col>
      <!-- Videos -->
      <b-col
        cols="12"
        xl="2"
        class="mb-2"
      >
        {{ $t(`forms.domain.hardware.videos`) }}
        <v-select
          v-model="videos"
          :options="availableHardware.videos"
          label="name"
          :reduce="element => element.id"
          @search:blur="v$.videos.$touch"
        >
          <template #search="{ attributes, events }">
            <input
              id="videos"
              class="vs__search"
              v-bind="attributes"
              v-on="events"
            >
          </template>
        </v-select>
        <div
          v-if="v$.videos.$error"
          id="videosError"
          class="text-danger"
        >
          {{ $t(`validations.${v$.videos.$errors[0].$validator}`, { property: `${$t("forms.domain.hardware.videos")}` }) }}
        </div>
      </b-col>
      <!-- Boot -->
      <b-col
        cols="12"
        xl="2"
        class="mb-2"
      >
        {{ $t(`forms.domain.hardware.boot`) }}
        <v-select
          v-model="bootOrder"
          :options="availableHardware.bootOrder"
          label="name"
          :reduce="element => element.id"
          @search:blur="v$.bootOrder.$touch"
        >
          <template #search="{ attributes, events }">
            <input
              id="bootOrder"
              class="vs__search"
              v-bind="attributes"
              v-on="events"
            >
          </template>
        </v-select>
        <div
          v-if="v$.bootOrder.$error"
          id="bootOrderError"
          class="text-danger"
        >
          {{ $t(`validations.${v$.bootOrder.$errors[0].$validator}`, { property: `${$t("forms.domain.hardware.boot")}` }) }}
        </div>
      </b-col>
      <!-- Disk Bus -->
      <b-col
        cols="12"
        xl="2"
        class="mb-2"
      >
        {{ $t(`forms.domain.hardware.disk-bus`) }}
        <v-select
          v-model="diskBus"
          :options="availableHardware.diskBus"
          label="name"
          :reduce="element => element.id"
          @search:blur="v$.diskBus.$touch"
        >
          <template #search="{ attributes, events }">
            <input
              id="diskBus"
              class="vs__search"
              v-bind="attributes"
              v-on="events"
            >
          </template>
        </v-select>
        <div
          v-if="v$.diskBus.$error"
          id="diskBusError"
          class="text-danger"
        >
          {{ $t(`validations.${v$.diskBus.$errors[0].$validator}`, { property: `${$t("forms.domain.hardware.disk-bus")}` }) }}
        </div>
      </b-col>
      <!-- Disk Size -->
      <b-col
        v-if="showDiskSize"
        cols="12"
        xl="2"
        class="mb-2"
      >
        {{ $t(`forms.domain.hardware.disk-size`) }}
        <v-select
          v-model="diskSize"
          :options="availableHardware.diskSize"
          label="name"
          @search:blur="v$.diskSize.$touch"
        >
          <template #search="{ attributes, events }">
            <input
              id="diskSize"
              class="vs__search"
              v-bind="attributes"
              v-on="events"
            >
          </template>
        </v-select>
        <div
          v-if="v$.diskSize.$error"
          id="diskSizeError"
          class="text-danger"
        >
          {{ $t(`validations.${v$.diskSize.$errors[0].$validator}`, { property: `${$t("forms.domain.hardware.disk-size")}` }) }}
        </div>
      </b-col>
      <!-- Interfaces -->
      <b-col
        cols="12"
        :xl="showDiskSize ? '10' : '12'"
        class="mb-2"
      >
        {{ $t(`forms.domain.hardware.interfaces`) }}
        <v-select
          v-model="interfaces"
          :options="availableHardware.interfaces"
          label="name"
          :close-on-select="false"
          :multiple="true"
          :reduce="element => element.id"
          @search:blur="v$.interfaces.$touch"
        >
          <template #search="{ attributes, events }">
            <input
              id="interfaces"
              class="vs__search"
              v-bind="attributes"
              v-on="events"
            >
          </template>
        </v-select>
        <div
          v-if="v$.interfaces.$error"
          id="interfacesError"
          class="text-danger"
        >
          {{ $t(`validations.${v$.interfaces.$errors[0].$validator}`, { property: `${$t("forms.domain.hardware.interfaces")}` }) }}
        </div>
        <span v-if="domain.kind === 'desktop'">
          <template
            v-for="(network, index) in interfaces"
          >
            <template v-if="index > 0">, </template>{{ `${availableHardware.interfaces.find(e => e.id === interfaces[index]).name} - ${interfacesMac[index] ? interfacesMac[index] : `${$t("validations.undefined")}` }` }}
          </template>
        </span>
      </b-col>
    </b-row>
  </div>
</template>

<script>
import { computed, onMounted, watch } from '@vue/composition-api'
import { hardwareWarningTitle } from '@/shared/constants'
import useVuelidate from '@vuelidate/core'
import { required, requiredIf } from '@vuelidate/validators'

export default {
  props: {
    showDiskSize: {
      required: false,
      type: Boolean,
      default: false
    }
  },
  setup (props, context) {
    const $store = context.root.$store
    const domain = computed(() => $store.getters.getDomain)
    onMounted(() => {
      $store.dispatch('fetchHardware')
    })
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
    const diskSize = computed({
      get: () => $store.getters.getDomain.hardware.diskSize,
      set: (value) => {
        domain.value.hardware.diskSize = value
        $store.commit('setDomain', domain.value)
      }
    })
    const graphics = computed({
      get: () => $store.getters.getDomain.hardware.graphics,
      set: (value) => {
        domain.value.hardware.graphics = value ? [value] : []
        $store.commit('setDomain', domain.value)
      }
    })
    const videos = computed({
      get: () => $store.getters.getDomain.hardware.videos,
      set: (value) => {
        domain.value.hardware.videos = value ? [value] : []
        $store.commit('setDomain', domain.value)
      }
    })
    const bootOrder = computed({
      get: () => $store.getters.getDomain.hardware.bootOrder,
      set: (value) => {
        domain.value.hardware.bootOrder = value ? [value] : []
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

    const interfacesMac = computed(() => $store.getters.getDomain.hardware.interfacesMac)

    // When creating a desktop from a media if the user has the iso boot option it will be selected by default
    watch(availableHardware, (availableHardware, prevVal) => {
      if (props.showDiskSize && availableHardware.bootOrder.filter(boot =>
        boot.id === 'iso'
      ).length > 0) {
        bootOrder.value = 'iso'
      }
    })

    return {
      vcpus,
      memory,
      diskSize,
      graphics,
      videos,
      bootOrder,
      diskBus,
      interfaces,
      interfacesMac,
      availableHardware,
      domain,
      hardwareWarningTitle,
      v$: useVuelidate({
        vcpus: {
          required
        },
        memory: {
          required
        },
        graphics: {
          required
        },
        videos: {
          required
        },
        bootOrder: {
          required
        },
        diskBus: {
          required
        },
        interfaces: {
          required
        },
        diskSize: {
          required: requiredIf(function () {
            return !!props.showDiskSize
          })
        }
      }, {
        vcpus,
        memory,
        graphics,
        videos,
        bootOrder,
        diskBus,
        interfaces,
        diskSize
      })
    }
  }
}
</script>
