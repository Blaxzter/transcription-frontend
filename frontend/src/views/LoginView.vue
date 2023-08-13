<template>
    <v-container :fluid="true" class="fill-height">
        <v-row align="center" justify="center">
            <v-col cols="12" sm="8" md="4">
                <v-card class="elevation-12" style="background-color: rgba(255, 255, 255, 0.8);">
                    <v-card-text>
                        <h1 class="text-h4 mb-4">Anmelden</h1>
                        <p class="mb-4">
                            Bitte melden Sie sich mit Ihrem Benutzernamen und Ihrem Passwort an.
                        </p>
                        <v-form ref="form" v-model="valid" @submit.prevent="login">
                            <v-text-field
                                    prepend-inner-icon="mdi-account"
                                    label="Username"
                                    name="username"
                                    v-model="username"
                                    :rules="usernameRules"
                                    required
                            ></v-text-field>
                            <v-text-field
                                    prepend-inner-icon="mdi-lock"
                                    label="Password"
                                    type="password"
                                    name="password"
                                    v-model="password"
                                    :rules="passwordRules"
                                    required
                            ></v-text-field>

                            <!--                           alert for error messages -->
                            <v-alert
                                    title="Alert title"
                                    class="mb-5"
                                    v-if="error"
                                    type="error"
                                    closable=""
                                    border="start"
                                    text="Benutzername oder Passwort falsch."
                            ></v-alert>

                            <v-btn
                                    color="primary"
                                    :disabled="!valid"
                                    type="submit"
                                    large
                                    class="w-100"
                                    variant="tonal"
                                    prepend-icon="mdi-send">Login
                            </v-btn>
                        </v-form>
                    </v-card-text>
                </v-card>
            </v-col>
        </v-row>
    </v-container>
</template>

<script>
import axios from 'axios';
import {useUserStore} from "@/stores/user";
import router from "@/router";

export default {
    name: "LoginView",
    data: () => ({
        userStore: useUserStore(),
        valid: false,
        username: '',
        password: '',
        error: false,
        usernameRules: [
            v => !!v || 'Benutzername ist erforderlich.',
        ],
        passwordRules: [
            v => !!v || 'Passwort ist erforderlich.',
        ],
    }),
    mounted() {
        console.log('LoginView mounted', this.userStore.is_logged_in)
        if (this.userStore.is_logged_in) {
            console.log('User is already logged in.')
            router.push({name: 'home'})
        }
    },
    methods: {
        async login() {
            if (await this.$refs.form.validate()) {
                try {
                    const form_data = new FormData();
                    form_data.append('username', this.username);
                    form_data.append('password', this.password);
                    const response = await axios.post('http://localhost:6545/token', form_data);
                    if (response.status !== 200) {
                        this.error = true;
                        return;
                    }

                    this.userStore.set_user(response.data.access_token);
                    router.push({name: 'home'})
                } catch (error) {
                    console.error('An error occurred during login:', error);
                    // Handle login error as needed
                    this.error = true;
                }
            }
        }
    }
}
</script>