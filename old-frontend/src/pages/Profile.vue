<template>
  <b-container
    id="content"
    fluid
    class=" w-100 px-5"
  >
    <b-row class="justify-content-center scrollable-div">
      <b-col
        cols="10"
        md="10"
        lg="10"
      >
        <b-row class="justify-content-center align-content-center">
          <b-col class="px-0">
            <b-row
              style="background: #fbfbfb;"
              class="m-0 rounded-bottom-30 rounded-top-30 pb-4"
            >
              <b-col
                cols="12"
                class="rounded-bottom-30"
              >
                <b-row class="justify-content-center">
                  <b-skeleton-wrapper
                    :loading="!profileLoaded"
                    class="card-body pt-4 d-flex flex-row flex-wrap justify-content-center"
                  >
                    <template #loading>
                      <ProfileCardSkeleton />
                    </template>
                    <b-col sm="10">
                      <b-row class="justify-content-center text-center py-4">
                        <!-- User info -->
                        <b-col
                          xl="6"
                          class="pt-4"
                        >
                          <b-avatar
                            :src="profile.photo"
                            size="8rem"
                          />
                          <!-- User name -->
                          <h4 class="font-weight-bold mt-4">
                            {{ profile.name }}
                          </h4>
                          <!-- User role -->
                          <h5 class="text-medium-gray">
                            {{ profile.username }}
                          </h5>
                          <template v-if="profile.provider === 'local'">
                            <PasswordModal />
                            <EmailVerificationModal v-if="config.showChangeEmailButton" />
                            <b-button
                              class="rounded-pill mx-1 pr-3 btn-dark-blue"
                              :title="$t('components.profile.change-password')"
                              @click="showPasswordModal(true)"
                            >
                              <b-icon
                                icon="lock-fill"
                                scale="0.75"
                              />
                              {{ $t('components.profile.change-password') }}
                            </b-button>
                            <b-button
                              v-if="config.showChangeEmailButton"
                              class="rounded-pill mr-2 pl-2 pr-3 btn-blue"
                              :title="$t('components.profile.change-email')"
                              @click="showEmailVerificationModal()"
                            >
                              <b-icon
                                icon="envelope-fill"
                                scale="0.75"
                              />
                              {{ $t('components.profile.change-email') }}
                            </b-button>
                          </template>
                          <b-button
                            class="rounded-pill mr-2 pl-2 pr-3 btn-green"
                            :title="$t('components.profile.change-email')"
                            @click="showResetVPNModalConfirmation()"
                          >
                            <b-icon
                              icon="shield-fill"
                              scale="0.75"
                            />
                            {{ $t('components.profile.reset-vpn') }}
                          </b-button>
                          <template v-if="showExportUserButton">
                            <b-button
                              class="rounded-pill mr-2 pl-2 pr-3 btn-red"
                              :title="$t('components.profile.export')"
                              @click="copyExportUserToken"
                            >
                              <b-icon
                                icon="file-earmark-arrow-down-fill"
                                scale="0.75"
                              />
                              {{ $t('components.profile.export') }}
                            </b-button>
                          </template>
                          <template v-if="showImportUserButton">
                            <ImportUserModal />
                            <b-button
                              class="rounded-pill mr-2 pl-2 pr-3 btn-red"
                              :title="$t('components.profile.import')"
                              @click="showImportUserModal(true)"
                            >
                              <b-icon
                                icon="file-earmark-arrow-up-fill"
                                scale="0.75"
                              />
                              {{ $t('components.profile.import') }}
                            </b-button>
                          </template>
                          <span>
                            <b-button
                              v-if="profile.userStorage.tokenWeb !== false"
                              class="rounded-pill btn-green mx-1 pr-3"
                              :title="$t('components.profile.info.user-storage')"
                              :href="profile.userStorage.tokenWeb"
                              target="_blank"
                            >
                              <b-icon
                                icon="hdd"
                              />
                              {{ $t('components.profile.info.user-storage') }}
                            </b-button>
                          </span>
                          <b-row class="text-left">
                            <b-col xl="12">
                              <b-row>
                                <b-col>
                                  <h6 class="font-weight-bold mt-4">
                                    {{ $t('components.profile.info.name') }}
                                  </h6>
                                </b-col>
                                <b-col>
                                  <h6 class="mt-4">
                                    {{ profile.name }}
                                  </h6>
                                </b-col>
                              </b-row>
                              <b-row>
                                <b-col>
                                  <h6 class="font-weight-bold mt-4">
                                    {{ $t('components.profile.info.email') }}
                                  </h6>
                                </b-col>
                                <b-col>
                                  <h6 class="mt-4">
                                    {{ profile.email }}
                                    <span v-if="config.showChangeEmailButton">
                                      <b-icon
                                        v-if="profile.emailVerified"
                                        variant="success"
                                        icon="patch-check-fill"
                                      />
                                      <template v-else>
                                        <b-tooltip
                                          :target="() => $refs['invalidTooltip']"
                                          :title="$t(`errors.not_verified`)"
                                          triggers="hover"
                                          custom-class="isard-tooltip"
                                          show
                                        />
                                        <b-icon
                                          ref="invalidTooltip"
                                          variant="warning"
                                          icon="patch-exclamation-fill"
                                        />
                                      </template>
                                    </span>
                                  </h6>
                                </b-col>
                              </b-row>
                              <b-row>
                                <b-col>
                                  <h6 class="font-weight-bold mt-4">
                                    {{ $t('components.profile.info.authentication') }}
                                  </h6>
                                </b-col>
                                <b-col>
                                  <h6 class="mt-4">
                                    {{ profile.provider }}
                                  </h6>
                                </b-col>
                              </b-row>
                              <b-row>
                                <b-col>
                                  <h6 class="font-weight-bold mt-4">
                                    {{ $t('components.profile.info.role') }}
                                  </h6>
                                </b-col>
                                <b-col>
                                  <h6 class="mt-4">
                                    {{ profile.role }}
                                  </h6>
                                </b-col>
                              </b-row>
                              <b-row>
                                <b-col>
                                  <h6 class="font-weight-bold mt-4">
                                    {{ $t('components.profile.info.category') }}
                                  </h6>
                                </b-col>
                                <b-col>
                                  <h6 class="mt-4">
                                    {{ profile.category }}
                                  </h6>
                                </b-col>
                              </b-row>
                              <b-row>
                                <b-col>
                                  <h6 class="font-weight-bold mt-4">
                                    {{ $t('components.profile.info.group') }}
                                  </h6>
                                </b-col>
                                <b-col>
                                  <h6 class="mt-4">
                                    {{ profile.group }}
                                  </h6>
                                </b-col>
                              </b-row>
                            </b-col>
                          </b-row>
                        </b-col>
                        <!-- User quota -->
                        <b-col
                          xl="6"
                          class="mt-4"
                        >
                          <h5 class="font-weight-bold">
                            {{ $t('components.profile.language') }}
                          </h5>
                          <b-row class="justify-content-center text-center">
                            <b-col cols="12">
                              <Language
                                class="mt-2 mt-md-4 mb-3"
                                :save-language="true"
                              />
                            </b-col>
                          </b-row>
                          <h5 class="font-weight-bold mt-4">
                            {{ $t('components.profile.quota.title', { restriction: $t(`components.profile.quota.restrictions.${profile.restrictionApplied}` )}) }}
                          </h5>
                          <b-row class="justify-content-center text-center pb-4">
                            <b-col cols="12">
                              <QuotaProgressBar
                                :title="$t('components.profile.quota.desktops')"
                                :value="profile.used.desktops"
                                :max="profile.quota.desktops"
                              />
                              <QuotaProgressBar
                                v-if="config.showTemporalTab"
                                :title="$t('components.profile.quota.volatile')"
                                :value="profile.used.volatile"
                                :max="profile.quota.volatile"
                              />
                              <QuotaProgressBar
                                v-if="profile.role.toLowerCase() !== 'user'"
                                :title="$t('components.profile.quota.templates')"
                                :value="profile.used.templates"
                                :max="profile.quota.templates"
                              />
                              <QuotaProgressBar
                                v-if="profile.role.toLowerCase() !== 'user'"
                                :title="$t('components.profile.quota.media')"
                                :value="profile.used.isos"
                                :max="profile.quota.isos"
                              />
                              <QuotaProgressBar
                                v-if="profile.role.toLowerCase() !== 'user'"
                                :title="$t('components.profile.quota.deployments_total')"
                                :value="profile.used.deploymentsTotal"
                                :max="profile.quota.deploymentsTotal"
                              />
                              <QuotaProgressBar
                                v-if="profile.role.toLowerCase() !== 'user'"
                                :title="$t('components.profile.quota.deployment_desktops')"
                                :value="profile.used.deploymentDesktops"
                                :max="profile.quota.deploymentDesktops"
                              />
                              <QuotaProgressBar
                                v-if="profile.role.toLowerCase() !== 'user'"
                                v-b-tooltip="{ title: `${$t('components.profile.quota.started_deployment_desktops.description')}`,
                                               placement: 'left',
                                               customClass: 'isard-tooltip',
                                               trigger: 'hover' }"
                                :title="$t('components.profile.quota.started_deployment_desktops.title')"
                                :value="profile.used.startedDeploymentDesktops"
                                :max="profile.quota.startedDeploymentDesktops"
                              />
                              <QuotaProgressBar
                                :title="$t('components.profile.quota.running')"
                                :value="profile.used.running"
                                :max="profile.quota.running"
                              />
                              <QuotaProgressBar
                                :title="$t('components.profile.quota.memory')"
                                :value="profile.used.memory"
                                :max="profile.quota.memory"
                              />
                              <QuotaProgressBar
                                :title="$t('components.profile.quota.vcpus')"
                                :value="profile.used.vcpus"
                                :max="profile.quota.vcpus"
                              />
                              <b-row>
                                <b-col
                                  cols="12"
                                  md="8"
                                  class="text-left"
                                >
                                  <h6 class="font-weight-bold mt-4">
                                    {{ $t('components.profile.quota.total-size') }}
                                  </h6>
                                </b-col>
                                <b-col
                                  cols="12"
                                  md="4"
                                  class="text-right"
                                >
                                  <h6 class="mt-4">
                                    {{ profile.used.totalSize ? profile.used.totalSize.toFixed(2) : 0.0 }} / {{ profile.quota === false ? '&infin;' : profile.quota.totalSize }}
                                  </h6>
                                </b-col>
                                <b-col cols="12">
                                  <b-progress
                                    :max="profile.quota === false ? 9999 : profile.quota.totalSize"
                                    animated
                                  >
                                    <b-progress-bar
                                      variant="primary"
                                      :value="profile.used.storageSize"
                                    >
                                      <b>{{ $t("components.navbar.desktops") }} / {{ $t("components.navbar.templates") }}</b>
                                    </b-progress-bar>
                                    <b-progress-bar
                                      variant="secondary"
                                      :value="profile.used.mediaSize"
                                    >
                                      <b>{{ $t("components.navbar.media") }}</b>
                                    </b-progress-bar>
                                  </b-progress>
                                </b-col>
                              </b-row>
                              <QuotaProgressBar
                                v-if="profile.userStorage && (profile.userStorage.providerQuota !== false)"
                                :title="$t('components.profile.quota.unit')"
                                :value="profile.userStorage.providerQuota.used"
                                :max="profile.userStorage.providerQuota.quota"
                              />
                            </b-col>
                          </b-row>
                        </b-col>
                      </b-row>
                    </b-col>
                  </b-skeleton-wrapper>
                </b-row>
              </b-col>
            </b-row>
          </b-col>
        </b-row>
      </b-col>
    </b-row>
  </b-container>
</template>

<script>
import { mapActions } from 'vuex'
import ProfileCardSkeleton from '@/components/profile/ProfileCardSkeleton.vue'
import Language from '@/components/Language.vue'
import PasswordModal from '@/components/profile/PasswordModal.vue'
import QuotaProgressBar from '@/components/profile/QuotaProgressBar.vue'
import { computed } from '@vue/composition-api'
import i18n from '@/i18n'
import EmailVerificationModal from '@/components/profile/EmailVerificationModal.vue'
import ImportUserModal from '@/components/profile/ImportUserModal.vue'

export default {
  components: {
    ProfileCardSkeleton,
    Language,
    PasswordModal,
    EmailVerificationModal,
    QuotaProgressBar,
    ImportUserModal
  },
  setup (_, context) {
    const $store = context.root.$store

    $store.dispatch('fetchProfile')
    const user = computed(() => $store.getters.getUser)
    const profile = computed(() => $store.getters.getProfile)
    const config = computed(() => $store.getters.getConfig)
    const exportUserToken = computed(() => $store.getters.getExportUserToken)
    const showExportUserButton = computed(() => $store.getters.getShowExportUserButton)
    const showImportUserButton = computed(() => $store.getters.getShowImportUserButton)

    $store.dispatch('fetchShowExportUserButton', user.value.provider)
    $store.dispatch('fetchShowImportUserButton', user.value.provider)

    const profileLoaded = computed(() => $store.getters.getProfileLoaded)
    const showEmailVerificationModal = () => {
      $store.dispatch('showEmailVerificationModal', true)
    }
    const yesAction = () => {
      context.root.$snotify.remove()
      $store.dispatch('resetVPN')
    }
    const showResetVPNModalConfirmation = (toast) => {
      context.root.$snotify.prompt(`${i18n.t('messages.confirmation.reset-vpn')}`, {
        position: 'centerTop',
        buttons: [
          { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
          { text: `${i18n.t('messages.no')}` }
        ],
        placeholder: ''
      })
    }

    const copyExportUserToken = () => {
      $store.dispatch('fetchExportUserToken').then(response => {
        navigator.clipboard.writeText(exportUserToken.value).then(() => {
          context.root.$snotify.success(i18n.t('messages.success.token-copied'))
        })
      })
    }

    const showImportUserModal = (value) => {
      $store.dispatch('showImportUserModal', value)
    }

    return { profile, profileLoaded, showEmailVerificationModal, config, showResetVPNModalConfirmation, copyExportUserToken, showExportUserButton, showImportUserButton, showImportUserModal }
  },
  destroyed () {
    this.$store.dispatch('resetProfileState')
  },
  methods: {
    ...mapActions([
      'showPasswordModal'
    ])
  }
}
</script>
<style scoped>
  .btn {
    margin: 4px;
  }
</style>
