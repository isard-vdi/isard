<template>
  <b-container
    fluid
    class="main-container pl-3 pr-3 pl-xl-5 pr-xl-5 pb-5 new-templates-list"
  >
    <b-form @submit.prevent="submitForm">
      <!-- Title -->
      <b-row clas="mt-2">
        <h4 class="p-1 mb-4 mt-2 mt-xl-4 ml-2">
          <strong>{{ $t('forms.new-desktop.title') }}</strong>
        </h4>
      </b-row>

      <DomainInfo />
      <DomainViewers />
      <DomainHardware :show-disk-size="true" />
      <DomainOSHardwareTemplate />

      <!-- Buttons -->
      <b-row align-h="end">
        <b-button
          size="md"
          class="btn-red rounded-pill mt-4 mr-2"
          @click="navigate('desktops')"
        >
          {{ $t('forms.cancel') }}
        </b-button>
        <b-button
          type="submit"
          size="md"
          class="btn-green rounded-pill mt-4 ml-2 mr-5"
        >
          {{ $t('forms.create') }}
        </b-button>
      </b-row>
    </b-form>
  </b-container>
</template>

<script>
import { computed, onUnmounted, onMounted } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import DomainViewers from '@/components/domain/DomainViewers.vue'
import DomainHardware from '@/components/domain/DomainHardware.vue'
import DomainInfo from '@/components/domain/DomainInfo.vue'
import DomainOSHardwareTemplate from '@/components/domain/DomainOSHardwareTemplate.vue'

export default {
  components: {
    DomainViewers,
    DomainHardware,
    DomainInfo,
    DomainOSHardwareTemplate
  },
  setup (props, context) {
    const $store = context.root.$store

    const navigate = (path) => {
      $store.dispatch('navigate', path)
    }
    onMounted(() => {
      if (media.value.id.length < 1) {
        $store.dispatch('navigate', 'media')
      }
    })

    const domain = computed(() => $store.getters.getDomain)
    const selectedOSTemplateId = computed(() => $store.getters.getSelectedOSTemplateId)
    const media = computed(() => $store.getters.getNewFromMedia)

    // Selected template validation
    const v$ = useVuelidate()

    // Send data to api
    const submitForm = () => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      // Parse viewers data
      const viewers = {}
      for (let i = 0; i < domain.value.guestProperties.viewers.length; i++) {
        Object.assign(viewers, domain.value.guestProperties.viewers[i])
      }
      // Create the data object that will be send
      const domainData = {
        media_id: media.value.id,
        kind: media.value.kind,
        xml_id: selectedOSTemplateId.value,
        name: domain.value.name,
        description: domain.value.description,
        guest_properties: {
          credentials: {
            username: domain.value.guestProperties.credentials.username,
            password: domain.value.guestProperties.credentials.password
          },
          fullscreen: domain.value.guestProperties.fullscreen,
          viewers: viewers
        },
        hardware: {
          boot_order: domain.value.hardware.bootOrder,
          disk_bus: domain.value.hardware.diskBus,
          disk_size: domain.value.hardware.diskSize,
          interfaces: domain.value.hardware.interfaces,
          memory: domain.value.hardware.memory,
          vcpus: domain.value.hardware.vcpus,
          videos: domain.value.hardware.videos
        }
      }
      $store.dispatch('createNewDesktopFromMedia', domainData)
    }

    onUnmounted(() => {
      $store.dispatch('resetDomainState')
      $store.dispatch('resetTemplatesState')
    })

    return {
      domain,
      submitForm,
      navigate,
      v$
    }
  }
}
</script>
