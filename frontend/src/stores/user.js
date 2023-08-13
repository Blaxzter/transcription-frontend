import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

// create user store
export const useUserStore = defineStore('user', () => {
    const user = ref(null)
    const user_image = ref(null)

    // getters
    const get_user = computed(() => user.value)
    const is_logged_in = computed(() => user.value !== null)

    function auto_login() {
        const token = localStorage.getItem('access_token')
        user.value = token
        return !!token;
    }

    function set_user(new_user) {
        user.value = new_user
        // set token in store
        localStorage.setItem('access_token', JSON.stringify(new_user))
    }

    return { user, user_image, get_user, is_logged_in, set_user, auto_login }

})
