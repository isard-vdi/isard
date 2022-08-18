<template>
  <b-container
    fluid
    class="main-container pl-3 pr-3 pl-xl-5 pr-xl-5 pb-5"
  >
    <b-form @submit.prevent="submitForm">
      <h4 class="my-4">
        <strong>{{ $t('forms.edit.title', {name: domainName } ) }}</strong>
      </h4>
      <b-row>
        <b-col
          class="px-4"
          cols="12"
        >
          <div
            id="scrollspy-nested"
          >
            <div id="info">
              <DomainInfo />
            </div>
            <div id="viewers">
              <DomainViewers />
            </div>
            <div id="hardware">
              <DomainHardware />
            </div>
            <div id="bookables">
              <DomainBookables />
            </div>
            <div id="media">
              <DomainMedia />
            </div>
            <div id="image">
              <DomainImage />
            </div>
          </div>
        </b-col>
      </b-row>

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
      // Create the data object that will be send
      const domainData = {
        id: domain.value.id,
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
          isos: domain.value.hardware.isos,
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