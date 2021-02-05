<template>
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
              <label for="user">Usuario</label>
              <InputText id="user" type="text" v-model.trim="user" />
            </div>
            <div class="p-field">
              <label for="password">Clave</label>
              <div>
                <InputText id="password" type="text" v-model.trim="password" />
              </div>
            </div>
            <div class="p-field">
              <label for="organization">Entidad</label>
              <Dropdown
                id="organization"
                v-model="dropdownValue"
                :options="dropdownValues"
                optionLabel="name"
                :filter="true"
                placeholder="Select an entity"
              >
                <template #value="slotProps">
                  <div v-if="slotProps.value">
                    <div>{{ slotProps.value.name }}</div>
                  </div>
                  <span v-else>
                    {{ slotProps.placeholder }}
                  </span>
                </template>
                <template #option="slotProps">
                  <div>
                    <div>{{ slotProps.option.name }}</div>
                  </div>
                </template>
              </Dropdown>
            </div>
            <div class="p-field">
              <label for="regcode">Codigo</label>
              <InputText id="regcode" type="text" v-model.trim="regcode" />
            </div>
            <div>
              <p v-if="!formIsValid">Enter a valid user and password</p>
              <p v-else>
                <br />
              </p>
            </div>
          </div>
        </template>
        <template #footer>
          <Button label="Login" icon="pi pi-check" @click="login" />
        </template>
      </Card>
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      user: '',
      password: '',
      regcode: '',
      formIsValid: true,
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
    login() {
      this.formIsValid = true;
      if (this.user === '' || this.password.length < 3) {
        this.formIsValid = false;
        return;
      }
      this.$router.push({ name: 'Admin' });
    }
  }
};
</script>

<style lang="scss">
#logo {
  margin-top: 20px;
  max-width: 50px;
}
</style>
