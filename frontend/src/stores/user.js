import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import router from '@/router'

// create user store
export const useUserStore = defineStore('user', () => {
  const user = ref(null)
  const user_image = ref(null)
  const user_file = ref(null)

  // getters
  const get_user = computed(() => user.value)
  const is_logged_in = computed(() => user.value !== null)
  const get_user_file = computed(() => user_file.value)

  function set_user_file(new_user_file) {
    user_file.value = new_user_file
  }

  function auto_login() {
    const token = localStorage.getItem('access_token')
    if (token) {
      try {
        user.value = JSON.parse(token)
      } catch (error) {
        console.error('Error parsing token:', error)
        localStorage.removeItem('access_token')
      }
    }
    return !!token
  }

  function set_user(new_user) {
    user.value = new_user
    // set token in store
    localStorage.setItem('access_token', JSON.stringify(new_user))
  }

  function logout() {
    user.value = null
    localStorage.removeItem('access_token')
    router.push('/login')
  }

  return {
    user,
    user_image,
    get_user,
    is_logged_in,
    set_user,
    auto_login,
    logout,
    set_user_file,
    get_user_file
  }
})
