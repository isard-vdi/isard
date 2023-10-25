<template>
  <b-container
    fluid
    class="main-container pl-3 pr-3 pl-xl-5 pr-xl-5 pb-5"
  >
    <b-form @submit.prevent="submitForm">
      <b-row clas="mt-2">
        <h4 class="p-1 mb-4 mt-2 mt-xl-4 ml-2">
          <strong>{{ $t('forms.edit.title', {name: domainName } ) }}</strong>
        </h4>
      </b-row>
      <DomainInfo />
      <DomainViewers />
      <DomainHardware />
      <DomainBookables />
      <DomainMedia />
      <DomainImage />

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
          {{ $t('forms.submit') }}
        </b-button>
      </b-row>
    </b-form>
  </b-container>
</template>

<script>
import { computed, onMounted, onUnmounted, ref, watch } from '@vue/composition-api'
import DomainInfo from '@/components/domain/DomainInfo.vue'
import DomainViewers from '@/components/domain/DomainViewers.vue'
import DomainHardware from '@/components/domain/DomainHardware.vue'
import DomainMedia from '@/components/domain/DomainMedia.vue'
import DomainBookables from '@/components/domain/DomainBookables.vue'
import DomainImage from '@/components/domain/DomainImage.vue'
import i18n from '@/i18n'
import useVuelidate from '@vuelidate/core'

export default {
  components: {
    DomainInfo,
    DomainViewers,
    DomainHardware,
    DomainMedia,
    DomainBookables,
    DomainImage
  },
  setup (props, context) {
    const $store = context.root.$store

    const v$ = useVuelidate()

    const domainId = computed(() => $store.getters.getEditDomainId)
    const domain = computed(() => $store.getters.getDomain)
    const domainName = ref('') // Displayed name in the form title

    watch(domain, (newVal, prevVal) => {
      domainName.value = newVal.name
    })

    const navigate = (path) => {
      $store.dispatch('navigate', path)
    }

    onMounted(() => {
      if (domainId.value.length < 1) {
        $store.dispatch('navigate', 'desktops')
      } else {
        $store.dispatch('fetchDomain', domainId.value)
        $store.dispatch('fetchDesktopImages')
      }
    })
    onUnmounted(() => {
      $store.dispatch('resetDomainState')
    })

    const submitForm = (toast) => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }
      if (domain.value.limitedHardware) {
        context.root.$snotify.clear()

        const yesAction = () => {
          context.root.$snotify.remove(toast.id)
          editDomain()
        }

        const noAction = (toast) => {
          context.root.$snotify.clear()
        }

        context.root.$snotify.prompt(`${i18n.t('messages.confirmation.edit-domain', { name: domainName.value })}`, {
          position: 'centerTop',
          buttons: [
            { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
            { text: `${i18n.t('messages.no')}`, action: noAction }
          ],
          placeholder: ''
        })
      } else {
        editDomain()
      }
    }

    const editDomain = () => {
      // Create the viewers object
      const viewers = {}
      for (let i = 0; i < domain.value.guestProperties.viewers.length; i++) {
        Object.assign(viewers, domain.value.guestProperties.viewers[i])
      }
      const isos = domain.value.hardware.isos.map((value) => {
        return { id: value.id }
      })
      // Create the data object that will be send
      const domainData = {
        id: domainId.value,
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
          disks: domain.value.hardware.disks,
          floppies: domain.value.hardware.floppies,
          interfaces: domain.value.hardware.interfaces,
          isos: isos,
          memory: domain.value.hardware.memory,
          vcpus: domain.value.hardware.vcpus,
          videos: domain.value.hardware.videos,
          reservables: domain.value.reservables
        },
        image: domain.value.image
      }
      $store.dispatch('editDomain', domainData)
    }

    return {
      domain,
      domainName,
      submitForm,
      navigate
    }
  }
}
</script>
