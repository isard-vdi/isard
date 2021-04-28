<template>
  <Language />
  <div class="p-d-flex p-jc-center">
    <div class="p-col-12 p-md-6 p-lg-4">
      <Card class="p-shadow-19">
        <template #header>
          <img id="logo" alt="IsardVDI" src="@/assets/logo.svg" />
        </template>
        <template #title>Login</template>
        <template #content>
          <div class="p-fluid">
            <div class="p-field">
              <label for="user">{{ $t('views.login.form.user.label') }}</label>
              <InputText
                id="user"
                v-model.trim="user"
                type="text"
                :placeholder="
                  $t('views.login.form.placeholder', {
                    field: $t('views.login.form.user.field')
                  })
                "
              />
            </div>
            <div class="p-field">
              <label for="password">{{
                $t('views.login.form.pass.label')
              }}</label>
              <div>
                <InputText
                  id="password"
                  v-model.trim="password"
                  type="text"
                  :placeholder="
                    $t('views.login.form.placeholder', {
                      field: $t('views.login.form.pass.field')
                    })
                  "
                />
              </div>
            </div>
            <div class="p-field">
              <label for="organization">{{
                $t('views.login.form.entity.label')
              }}</label>
              <Dropdown
                id="organization"
                v-model="dropdownValue"
                :options="dropdownValues"
                option-label="name"
                :filter="true"
                :placeholder="
                  $t('views.login.form.placeholder', {
                    field: $t('views.login.form.entity.field')
                  })
                "
              >
                <template #value="slotProps">
                  <div v-if="slotProps.value">
                    <div>{{ slotProps.value.name }}</div>
                  </div>
                  <span v-else>
                    {{ slotProps.placeholder }}
                  </span>
                </template>
                <template #option="slotProps"
                  ><div>
                    <div>{{ slotProps.option.name }}</div>
                  </div>
                </template>
              </Dropdown>
            </div>
            <div class="p-field">
              <label for="regcode">{{
                $t('views.login.form.code.label')
              }}</label>
              <InputText
                id="regcode"
                v-model.trim="regcode"
                type="text"
                :placeholder="
                  $t('views.login.form.placeholder', {
                    field: $t('views.login.form.code.field')
                  })
                "
              />
            </div>
            <div>
              <p v-if="!formIsValid">{{ $t('views.login.form.error') }}</p>
              <p v-else>
                <br />
              </p>
            </div>
          </div>
        </template>
        <template #footer>
          <Button label="Login" icon="pi pi-check" @click="buttLogin" />
        </template>
      </Card>
    </div>
  </div>
</template>

<script>
import Language from '@/components/Language.vue';
import { ref } from 'vue';
import { useStore } from 'vuex';
import { ActionTypes } from '@/store/actions';
import { LOGIN_ENTITY } from '@/config/constants';
import InputText from 'primevue/inputtext';
import Button from 'primevue/button';
import Dropdown from 'primevue/dropdown';
import Card from 'primevue/card';

export default {
  components: {
    Language: Language,
    InputText: InputText,
    Button: Button,
    Dropdown: Dropdown,
    Card: Card
  },
  setup(props, context) {
    const store = useStore();

    const user = ref('');
    const password = ref('');
    const organization = ref('');
    const formIsValid = ref(true);

    const buttLogin = () => {
      formIsValid.value = true;
      if (user.value === '' || password.value.length < 3) {
        formIsValid.value = false;
        return;
      }
      store.dispatch(ActionTypes.DO_LOCAL_LOGIN, {
        usr: user.value,
        psw: password.value,
        entity: LOGIN_ENTITY
      });
    };

    return {
      buttLogin,
      formIsValid,
      user,
      password
    };
  },
  data() {
    return {
      regcode: '',
      mode: 'login',
      dropdownValue: null,
      dropdownValues: [
        { name: 'Institut Coromines', code: '1er' },
        { name: 'Institut Carles III', code: 'er' },
        { name: 'Escola Arts', code: '3' }
      ]
    };
  },
  methods: {
    login() {}
  }
};
</script>

<style lang="scss">
#logo {
  margin-top: 20px;
  max-width: 50px;
}
</style>
