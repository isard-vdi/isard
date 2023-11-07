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
                          <div
                            v-if="profile.provider === 'local'"
                            class="pt-1"
                          >
                            <PasswordModal />
                            <b-button
                              class="rounded-pill mr-2 pl-2 pr-3 btn-dark-blue"
                              :title="$t('components.profile.change-password')"
                              @click="showPasswordModal(true)"
                            >
                              <b-icon
                                icon="lock-fill"
                                scale="0.75"
                              />
                              {{ $t('components.profile.change-password') }}
                            </b-button>
                          </div>
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
                              <b-row
                                v-if="profile.userStorage.tokenWeb !== false"
                              >
                                <b-col>
                                  <h6 class="font-weight-bold mt-4">
                                    {{ $t('components.profile.info.user-storage') }}
                                  </h6>
                                </b-col>
                                <b-col>
                                  <h6 class="mt-4">
                                    <a :href="profile.userStorage.tokenWeb">{{ profile.userStorage.tokenWeb }}</a>
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
                                :title="$t('components.profile.quota.templates')"
                                :value="profile.used.templates"
                                :max="profile.quota.templates"
                              />
                              <QuotaProgressBar
                                :title="$t('components.profile.quota.media')"
                                :value="profile.used.isos"
                                :max="profile.quota.isos"
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
                                v-if="profile.userStorage.providerQuota !== false"
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

export default {
  components: {
    ProfileCardSkeleton,
    Language,
    PasswordModal,
    QuotaProgressBar
  },
  setup (_, context) {
    const $store = context.root.$store

    $store.dispatch('fetchProfile')
    const profile = computed(() => $store.getters.getProfile)
    const profileLoaded = computed(() => $store.getters.getProfileLoaded)

    return { profile, profileLoaded }
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
