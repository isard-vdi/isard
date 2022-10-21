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
          <!-- <b-skeleton-wrapper :loading="false" class='card-body pt-4 d-flex flex-row flex-wrap justify-content-start'>
            <template #loading>
              <profile-card-skeleton></profile-card-skeleton>
            </template>
            <ProfileCard :profile="getProfile"/>
          </b-skeleton-wrapper> -->
          <b-col class="px-0">
            <b-row
              style="background: #fbfbfb;"
              class="m-0 rounded-bottom-30 rounded-top-30 pt-4 pb-4"
            >
              <!-- MACHINE ACCESS METHODS -->
              <b-col
                cols="12"
                class="rounded-bottom-30 pt-4"
              >
                <!-- machine access methods  -->
                <b-row class="justify-content-center">
                  <!-- single method start -->
                  <b-skeleton-wrapper
                    :loading="!getProfileLoaded"
                    class="card-body pt-4 d-flex flex-row flex-wrap justify-content-center"
                  >
                    <template #loading>
                      <ProfileCardSkeleton />
                    </template>
                    <b-col sm="10">
                      <b-row class="justify-content-center text-center py-4">
                        <!-- User info -->
                        <b-col xl="6">
                          <b-avatar
                            :src="getProfile.photo"
                            size="8rem"
                          />
                          <!-- User name -->
                          <h4 class="font-weight-bold mt-4">
                            {{ getProfile.name }}
                          </h4>
                          <!-- User role -->
                          <h5 class="text-medium-gray">
                            {{ getProfile.username }}
                          </h5>
                          <div
                            v-if="getProfile.provider === 'local'"
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
                                    {{ getProfile.name }}
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
                                    {{ getProfile.email }}
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
                                    {{ getProfile.provider }}
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
                                    {{ getProfile.role }}
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
                                    {{ getProfile.category }}
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
                                    {{ getProfile.group }}
                                  </h6>
                                </b-col>
                              </b-row>
                            </b-col>
                          </b-row>
                        </b-col>
                        <!-- User quota -->
                        <b-col xl="6">
                          <h5 class="font-weight-bold mt-4">
                            {{ $t('components.profile.language') }}
                          </h5>
                          <b-row class="justify-content-center text-center">
                            <b-col cols="12">
                              <Language class="mt-2 mt-md-4 mb-3" />
                            </b-col>
                          </b-row>
                          <h5 class="font-weight-bold mt-4">
                            {{ $t('components.profile.quota.title', { restriction: $t(`components.profile.quota.restrictions.${getProfile.restrictionApplied}` )}) }}
                          </h5>
                          <b-row class="justify-content-center text-center pb-4">
                            <b-col cols="12">
                              <QuotaProgressBar
                                :title="$t('components.profile.quota.desktops')"
                                :value="getProfile.used.desktops"
                                :max="getProfile.quota.desktops"
                              />
                              <QuotaProgressBar
                                :title="$t('components.profile.quota.templates')"
                                :value="getProfile.used.templates"
                                :max="getProfile.quota.templates"
                              />
                              <QuotaProgressBar
                                :title="$t('components.profile.quota.media')"
                                :value="getProfile.used.isos"
                                :max="getProfile.quota.isos"
                              />
                              <QuotaProgressBar
                                :title="$t('components.profile.quota.running')"
                                :value="getProfile.used.running"
                                :max="getProfile.quota.running"
                              />
                              <QuotaProgressBar
                                :title="$t('components.profile.quota.memory')"
                                :value="getProfile.used.memory"
                                :max="getProfile.quota.memory"
                              />
                              <QuotaProgressBar
                                :title="$t('components.profile.quota.vcpus')"
                                :value="getProfile.used.vcpus"
                                :max="getProfile.quota.vcpus"
                              />
                            </b-col>
                          </b-row>
                        </b-col>
                      </b-row>
                    </b-col>
                  <!-- single method end -->
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
import { mapGetters, mapActions } from 'vuex'
import ProfileCardSkeleton from '@/components/profile/ProfileCardSkeleton.vue'
import Language from '@/components/Language.vue'
import PasswordModal from '@/components/profile/PasswordModal.vue'
import QuotaProgressBar from '@/components/profile/QuotaProgressBar.vue'

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
  },
  computed: {
    ...mapGetters([
      'getUser',
      'getProfile',
      'getProfileLoaded'
    ])
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
