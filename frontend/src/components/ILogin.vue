<template>
	<div class="p-grid p-fluid">
		<div class="card login-card">
				<h5>Login</h5>
				<div class="p-field p-grid">
					<label for="user" class="p-col-12 p-mb-2 p-md-2 p-mb-md-0">Usuario</label>
					<div class="p-col-12 p-md-10">
						<InputText id="user" type="text" v-model.trim="user"/>
					</div>
				</div>
				<div class="p-field p-grid">
					<label for="password" class="p-col-12 p-mb-2 p-md-2 p-mb-md-0">Clave</label>
					<div class="p-col-12 p-md-10">
						<InputText id="password" type="text" v-model.trim="password"/>
					</div>
				</div>
				<div class="p-field p-grid dropdown">
					<label for="organization" class="p-col-12 p-mb-2 p-md-2 p-mb-md-0">Entidad</label>
					<div class="p-col-12 p-md-10">
						<Dropdown id="organization" v-model="dropdownValue" :options="dropdownValues" optionLabel="name" placeholder="Select" />
					</div>
				</div>
				<div class="p-field p-grid">
					<label for="regcode" class="p-col-12 p-mb-2 p-md-2 p-mb-md-0">Codigo</label>
					<div class="p-col-12 p-md-10">
						<InputText id="regcode" type="text" v-model.trim="regcode"/>
					</div>
				</div>
				<div class="error-message">
					<p v-if="!formIsValid">
						Enter a valid user and password
					</p>
					<p v-else>
						<br/>
					</p>
				</div>
				<div class="login-button">
					<Button label="Login" class="p-button-raised p-button-secondary p-mr-2 p-mb-2" @click="login"/>
				</div>
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
					{name: 'Institut Coromines', code: '1er'},
					{name: 'Institut Carles III', code: 'er'},
					{name: 'Escola Arts', code: '3'}
                    ],
            }
		},
		methods: {
			login() {
				this.formIsValid = true;
				if (this.user === '' || this.password.length < 3) {
					this.formIsValid = false;
					return;
				}
				this.$router.push('/dashboard')
			},
			switchAuthMode() {

			}
		}
}
</script>

<style lang="scss">
    .login-card {
        width: 400px !important;
        background-color: rgb(82, 153, 165) !important;
	}
	
	.login-button  {
		text-align: end;
		margin-left: 14em;
	}

	.dropdown {
		text-align: left;
	}

	.error-message {
		margin-bottom: 1em;
	}
</style>