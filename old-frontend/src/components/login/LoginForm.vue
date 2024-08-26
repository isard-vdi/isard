<template>
  <!-- Login form -->
  <b-form
    v-if="showLoginForm"
    ref="loginForm"
    class="m-0"
    method="POST"
    enctype="multipart/form-data"
    @submit.prevent="login('form')"
  >
    <!-- Error message -->
    <b-alert
      v-model="showDismissibleAlert"
      dismissible
      variant="danger"
    >
      {{ $t(errorMessage) }}
    </b-alert>
    <b-overlay
      :show="loading"
      rounded
      opacity="0"
      spinner-small
      spinner-variant="success"
    >
      <!-- Category selection -->
      <v-select
        v-if="!categoryByPath && categories.length > 1"
        v-model="category"
        class="mb-3"
        size="md"
        :options="categoriesSelect"
        :reduce="category => category.value"
        :placeholder="$t('views.login.form.select-category')"
      >
        <template #search="{attributes, events}">
          <input
            id="category"
            class="vs__search"
            style="margin-bottom: 0px"
            v-bind="attributes"
            v-on="events"
          >
        </template>
      </v-select>
      <b-form-input
        id="usr"
        v-model="usr"
        type="text"
        autocomplete="off"
        :placeholder="$t('views.login.form.usr')"
        :state="v$.usr.$error ? false : null"
        :disabled="loading"
        @blur="v$.usr.$touch"
      />
      <b-form-input
        id="pwd"
        v-model="pwd"
        type="password"
        autocomplete="off"
        :placeholder="$t('views.login.form.pwd')"
        :state="v$.pwd.$error ? false : null"
        :disabled="loading"
        @blur="v$.pwd.$touch"
      />
      <b-link @click="redirectForgotPassword()">
        {{ $t('views.login.form.forgot-password') }}
      </b-link>
      <b-button
        type="submit"
        :disabled="loading"
        size="lg"
        class="btn-green w-100 rounded-pill mt-2 mt-md-5"
      >
        {{ $t('views.login.form.login') }}
      </b-button>
    </b-overlay>
    <div v-if="showLoginProviders">
      <hr
        class="m-4"
        style="border-bottom: 1px solid #ececec;"
      >
      <div class="d-flex flex-row flex-wrap justify-content-center align-items-center">
        <p class="w-100 text-center">
          {{ $t('views.login.other-logins') }}
        </p>
        <b-button
          v-for="provider in providers"
          :key="provider"
          :class="'rounded-pill mt-0 btn-sm login-btn btn-' + provider.toLowerCase()"
          @click="login(provider.toLowerCase())"
        >
          <font-awesome-icon
            v-if="!['saml'].includes(provider)"
            :icon="['fab', provider.toLowerCase()]"
          />
          {{ provider }}
        </b-button>
      </div>
    </div>
  </b-form>
</template>

<script>
import { authenticationSegment, sessionCookieName } from '@/shared/constants'
import { watch, ref, computed, onBeforeMount } from '@vue/composition-api'
import useVuelidate from '@vuelidate/core'
import { required } from '@vuelidate/validators'
import { getCookie } from 'tiny-cookie'

export default {
  name: 'LoginForm',
  setup (props, context) {
    const $store = context.root.$store
    const category = ref('')
    const loading = ref(false)
    const usr = ref('')
    const pwd = ref('')
    const showDismissibleAlert = ref(false)
    const loginForm = ref(null)

    const providers = computed(() => $store.getters.getProviders)
    const categories = computed(() => $store.getters.getCategories)
    const urlCategory = computed(() => $store.getters.getCategory)
    const errorMessage = computed(() => $store.getters.getPageErrorMessage)

    const categoryByPath = computed(() => context.root.$route.params.customUrlName !== undefined)
    const categoryName = computed(() => urlCategory.value.name ? urlCategory.value.name : '')
    const showLoginProviders = computed(() => showLoginForm.value && providers.value.length)
    const showLoginExtras = computed(() => showLoginForm || showLoginProviders)
    const categoriesSelect = computed(() => categories.value.map(category =>
      ({
        value: category.id,
        label: category.name
      })
    ))
    const showLoginForm = computed(() => categories.value.length || categoryByPath.value)

    onBeforeMount(() => {
      if (getCookie(sessionCookieName)) {
        $store.dispatch('navigate', 'desktops')
      }
      $store.dispatch('fetchProviders')
      $store.dispatch('fetchCategories').then(() => {
        let defaultCategory = ''
        if (categories.value.length === 1) {
          defaultCategory = categories.value[0].id
        }
        if (categoryByPath.value) {
          const customUrlName = context.root.$route.params.customUrlName
          $store.dispatch('fetchCategory', customUrlName).then(() => {
            category.value = urlCategory.value.id
          })
        } else {
          if (categories.value.map(i => i.id).includes(localStorage.category)) {
            category.value = localStorage.category
          } else {
            category.value = defaultCategory
          }
        }
      })
    })

    watch(category, (newVal, prevVal) => {
      if (!categoryByPath.value) {
        localStorage.category = category.value
      }
    })

    const v$ = useVuelidate({
      category: {
        required
      },
      usr: {
        required
      },
      pwd: {
        required
      }
    }, {
      category,
      usr,
      pwd
    })

    const login = (provider) => {
      if (provider === 'form') {
        v$.value.$touch()
        if (v$.value.$invalid) {
          document.getElementById(v$.value.$errors[0].$property).focus()
          return
        }
        loading.value = true
        const data = new FormData()
        data.append('category_id', category.value)
        data.append('provider', provider)
        data.append('username', usr.value)
        data.append('password', pwd.value)
        $store
          .dispatch('login', data)
          .catch(e => {
            console.log(e)
            showDismissibleAlert.value = true
            loading.value = false
            $store.dispatch('handleLoginError', e)
          })
      } else {
        if (category.value) {
          loginForm.value.action = `${authenticationSegment}/login?provider=${provider}&category_id=${category.value}&redirect=/`
          loginForm.value.submit()
        } else {
          v$.value.$reset()
          document.getElementById('category').focus()
        }
      }
    }

    const redirectForgotPassword = () => {
      if (category.value) {
        context.root.$router.push({ name: 'ForgotPassword', query: { categoryId: category.value } })
      } else {
        v$.value.$reset()
        document.getElementById('category').focus()
      }
    }

    return {
      category,
      loading,
      usr,
      pwd,
      showDismissibleAlert,
      providers,
      categories,
      urlCategory,
      errorMessage,
      categoryByPath,
      categoryName,
      showLoginProviders,
      showLoginExtras,
      categoriesSelect,
      showLoginForm,
      v$,
      login,
      loginForm,
      authenticationSegment,
      redirectForgotPassword
    }
  }
}
</script>

<style scoped>
#login {
  text-align: center;
}

#powered-by {
  margin: 4rem;
}
#isard-logo {
  width: 3rem;
  margin: -3rem 0.5rem 0 0.5rem;
}

#login form {
  margin: 25px;
}

#login form input {
  margin-bottom: 18px;
}

.login-btn {
  margin: 10px;
}

.login-btn svg {
  margin-right: 10px;
}

/* background -> brand color; border -> background: darken(brand color, 5%); */
.btn-github {
  color: #fff !important;
  background-color: #333 !important;
  border-color: #262626 !important;
}

.btn-google {
  color: #fff !important;
  background-color: #4285f4 !important;
  border-color: #2a75f3 !important;
}

#powered-by a {
  color: inherit !important;
  text-decoration: none !important;
}
</style>
