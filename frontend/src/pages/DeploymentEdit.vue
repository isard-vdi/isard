<template>
  <b-container
    fluid
    class="main-container pl-3 pr-3 pl-xl-5 pr-xl-5 pb-5 new-templates-list"
  >
    <b-form @submit.prevent="submitForm">
      <!-- Title -->
      <b-row clas="mt-2">
        <h4 class="p-1 mb-4 mt-2 mt-xl-4 ml-2">
          <strong>{{ $t('forms.edit.title', {name: deploymentName}) }}</strong>
        </h4>
      </b-row>

      <!-- Name -->
      <b-row>
        <b-col
          cols="4"
          xl="2"
        >
          <label for="deploymentName">{{ $t('forms.new-deployment.name') }}</label>
        </b-col>
        <b-col
          cols="6"
          xl="4"
          class="mb-4"
        >
          <b-form-input
            id="deploymentName"
            v-model="deploymentName"
            type="text"
            size="sm"
            :state="v$.deploymentName.$error ? false : null"
            @blur="v$.deploymentName.$touch"
          />
          <b-form-invalid-feedback
            v-if="v$.deploymentName.$error"
            id="deploymentNameError"
          >
            {{ $t(`validations.${v$.deploymentName.$errors[0].$validator}`, { property: $t('forms.new-deployment.name'), model: deploymentName.length, min: 4, max: 50 }) }}
          </b-form-invalid-feedback>
        </b-col>
      </b-row>

      <b-row clas="mt-2">
        <h4 class="p-1 mb-4 mt-2 mt-xl-4 ml-2">
          <strong>{{ $t('forms.edit-deployment.desktop.title') }}</strong>
        </h4>
      </b-row>

      <DomainInfo />

      <!-- Advanced options section title -->
      <b-row class="mt-2 mt-xl-5">
        <h5
          class="p-2 mt-2 cursor-pointer"
          @click="collapseVisible = !collapseVisible"
        >
          <strong>{{ $t('forms.new-desktop.section-title-advanced') }}</strong>
          <b-icon
            class="ml-2"
            :icon="collapseVisible ? 'chevron-up' : 'chevron-down'"
          />
        </h5>
      </b-row>

      <div>
        <b-collapse
          id="collapse-advanced"
          v-model="collapseVisible"
          class="mt-2"
        >
          <DomainViewers />
          <DomainHardware />
          <DomainBookables />
          <DomainMedia />
          <DeploymentUserPermissions />
          <DomainImage />
        </b-collapse>
      </div>

      <!-- Buttons -->
      <b-row align-h="end">
        <b-button
          size="md"
          class="btn-red rounded-pill mt-4 mr-2"
          @click="navigate('deployments')"
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
import i18n from '@/i18n'
import { onMounted, ref, computed, onUnmounted } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required, maxLength, minLength } from '@vuelidate/validators'
import DomainInfo from '@/components/domain/DomainInfo.vue'
import DomainViewers from '@/components/domain/DomainViewers.vue'
import DomainHardware from '@/components/domain/DomainHardware.vue'
import DomainMedia from '@/components/domain/DomainMedia.vue'
import DomainBookables from '@/components/domain/DomainBookables.vue'
import DomainImage from '@/components/domain/DomainImage.vue'
import DeploymentUserPermissions from '@/components/deployments/DeploymentUserPermissions.vue'

// const inputFormat = helpers.regex('inputFormat', /^1(3|4|5|7|8)\d{9}$/) // /^\D*7(\D*\d){12}\D*$'
const inputFormat = value => /^[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$/.test(value)

export default {
  components: {
    DomainInfo,
    DomainViewers,
    DomainHardware,
    DomainMedia,
    DomainBookables,
    DomainImage,
    DeploymentUserPermissions
  },
  setup (props, context) {
    const $store = context.root.$store
    onMounted(() => {
      const deploymentId = context.root.$route.params.id
      if (deploymentId.length < 1) {
        navigate('deployments')
      } else {
        $store.dispatch('fetchDeploymentInfo', deploymentId)
        $store.dispatch('fetchDesktopImages')
      }
    })

    onUnmounted(() => {
      $store.dispatch('resetAllowedState')
      $store.dispatch('resetDomainState')
      $store.dispatch('resetDeploymentState')
    })

    const navigate = (path) => {
      $store.dispatch('navigate', path)
    }

    const deploymentName = computed({
      get: () => $store.getters.getDeployment.name,
      set: (value) => {
        deployment.value.name = value
        $store.commit('setDeployment', deployment.value)
      }
    })
    const visible = ref(false)
    const collapseVisible = ref(false)

    const domain = computed(() => $store.getters.getDomain)
    const deployment = computed(() => $store.getters.getDeployment)
    const groupsChecked = computed(() => $store.getters.getGroupsChecked)
    const selectedGroups = computed(() => $store.getters.getSelectedGroups)
    const usersChecked = computed(() => $store.getters.getUsersChecked)
    const selectedUsers = computed(() => $store.getters.getSelectedUsers)
    const userPermissions = computed(() => $store.getters.getPermissions)

    const v$ = useVuelidate({
      deploymentName: {
        required,
        maxLengthValue: maxLength(50),
        minLengthValue: minLength(4),
        inputFormat
      },
      description: {
        maxLengthValue: maxLength(255)
      }
    }, { deploymentName })

    const submitForm = (toast) => {
      // Check if the form is valid
      v$.value.$touch()
      if (v$.value.$invalid) {
        console.log('NOT VALID')
        console.log(v$.value.$errors)
        document.getElementById(v$.value.$errors[0].$property).focus()
        return
      }

      const showConfirmation = () => {
        context.root.$snotify.clear()
        const yesAction = () => {
          context.root.$snotify.remove(toast.id)
          // Parse viewers data
          const viewers = {}
          for (let i = 0; i < domain.value.guestProperties.viewers.length; i++) {
            Object.assign(viewers, domain.value.guestProperties.viewers[i])
          }
          // Parse isos data
          const isos = domain.value.hardware.isos.map((value) => {
            return { id: value.id }
          })
          $store.dispatch('editDeployment',
            {
              id: domain.value.id,
              name: deploymentName.value,
              desktop_name: domain.value.name,
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
              image: domain.value.image,
              user_permissions: userPermissions.value
            }
          )
        }

        const noAction = (toast) => {
          context.root.$snotify.clear()
        }

        context.root.$snotify.prompt(`${i18n.t('messages.confirmation.edit-deployment', { name: deploymentName.value })}`, {
          position: 'centerTop',
          buttons: [
            { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
            { text: `${i18n.t('messages.no')}`, action: noAction }
          ],
          placeholder: ''
        })
      }
      showConfirmation()
    }

    return {
      deploymentName,
      visible,
      groupsChecked,
      selectedGroups,
      usersChecked,
      selectedUsers,
      // userPermissions,
      v$,
      submitForm,
      navigate,
      collapseVisible
    }
  }
}
</script>
