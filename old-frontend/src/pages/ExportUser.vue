<template>
  <b-container
    fluid
    class="export-user-container"
  >
    <b-row
      id="export-user-card"
      class="justify-content-center py-5"
    >
      <b-form class="w-75">
        <div
          class="d-flex align-items-left"
        >
          <b-button
            variant="link"
            size="lg"
            style="box-shadow:none;--webkit-box-shadow:none;color:rgb(17, 73, 84) !important"
            @click="goBack"
          >
            <b-icon icon="arrow-left-short" /> {{ $t('views.export-user.back') }}
          </b-button>
        </div>
        <div
          id="new-logo-wrapper"
        >
          <Logo />
        </div>
        <h2
          class="my-3"
          style="color: #44403C !important"
        >
          <strong>{{ $t('views.export-user.title') }}</strong>
        </h2>
        <h4>{{ $t('views.export-user.description') }}</h4>
        <b-row class="p-3 ">
          <ul>
            <li> {{ $t('views.export-user.migration-instructions1') }}</li>
            <li> {{ $t('views.export-user.migration-instructions2') }}</li>
          </ul>
          <p><b>{{ $t('views.export-user.warning') }}:</b> {{ $t('views.export-user.migration-warning') }}</p>
        </b-row>
        <div
          v-if="!exportUserToken"
          style="height:4rem;"
        />
        <b-form-group
          v-if="exportUserToken"
          label-for="token-input"
          class="mt-3"
        >
          <b-input-group>
            <b-input-group-append>
              <b-button
                size="md"
                style="background-color: #114954;"
                variant="secondary"
                :title="$t('views.export-user.copy')"
                @click="copyExportUserToken"
              >
                <b-icon
                  icon="clipboard"
                />
                {{ $t('views.export-user.copy-token') }}
              </b-button>
            </b-input-group-append>
            <b-form-input
              id="token-input"
              v-model="exportUserToken"
              class="text-truncate"
              disabled
            />
          </b-input-group>
          <b-row class="text-danger m-2">
            <b-icon
              class="m-1"
              variant="danger"
              icon="exclamation-triangle-fill"
            /> {{ $t('views.export-user.generate-token-warning') }}
          </b-row>
        </b-form-group>
        <b-row
          class="pt-4"
        >
          <b-button
            size="md"
            style="background-color: #114954; border-radius: .5rem !important; border: none !important; font-weight: 600 !important;"
            class="m-1 mb-4"
            :style="{ cursor: exportUserToken ? 'not-allowed' : 'pointer' }"
            :disabled="exportUserToken ? true : false"
            @click="generateToken"
          >
            {{ $t('views.export-user.generate-token') }}
          </b-button>
          <b-button
            size="md"
            style="background-color: #bb1414; border-radius: .5rem !important; border: none !important; font-weight: 600 !important;"
            class="m-1 mb-4"
            :title="$t('views.export-user.logout-tooltip')"
            :style="{ cursor: !exportUserToken ? 'not-allowed' : 'pointer' }"
            :disabled="!exportUserToken ? true : false"
            @click="logout"
          >
            {{ $t('views.export-user.logout') }}
          </b-button>
        </b-row>
      </b-form>
    </b-row>
    <img
      id="bottom-right-mountains"
      src="/img/mountains.8b78aee0.svg"
      class=""
    >
  </b-container>
</template>

<script>
import Logo from '@/components/Logo.vue'
import { computed } from '@vue/composition-api'
import i18n from '@/i18n'
import { ErrorUtils } from '@/utils/errorUtils'

export default {
  components: { Logo },
  setup (_, context) {
    const $store = context.root.$store
    const exportUserToken = computed(() => $store.getters.getExportUserToken)

    const generateToken = () => {
      $store.dispatch('generateExportUserToken')
    }

    const logout = () => {
      $store.dispatch('logout')
    }
    const copyExportUserToken = () => {
      navigator.clipboard.writeText(exportUserToken.value).then(() => {
        ErrorUtils.showInfoMessage(context.root.$snotify, i18n.t('messages.info.token-copied'))
      })
    }

    const goBack = () => {
      window.location.pathname = '/Desktops'
    }

    return {
      exportUserToken,
      generateToken,
      copyExportUserToken,
      goBack,
      logout
    }
  }
}
</script>

<style>
#export-user-card {
    background-color: #ffffff !important;
    margin: 4rem;
    position: relative;
    border-radius: 1.5rem;
    border: 1px solid #D7D3D0;
    z-index: 2;
    box-shadow: 0px 24px 48px -12px rgba(16, 24, 40, 0.18);
}

.export-user-container {
  height: calc(100vh);
  overflow-y: auto;
  background-color: #fbf7ed !important;
  font-family: 'Montserrat', 'sans-serif';
}

#bottom-right-mountains {
    position: absolute;
    bottom: 0;
    right: 0;
    z-index: 1;
}

#export-user-card button[disabled] {
  background-color: grey !important;
}

</style>
