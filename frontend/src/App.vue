<script setup>
import { RouterView } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { onMounted } from 'vue'
import axios from 'axios'

const user = useUserStore()

onMounted(() => {
  user.auto_login()
})

// add axios interceptor to add auth header to every request and if 401 is received, logout
axios.interceptors.request.use(
  function (config) {
    if (user.get_user) config.headers.Authorization = 'Bearer ' + user.get_user
    return config
  },
  function (error) {
    return Promise.reject(error)
  }
)

axios.interceptors.response.use(
  function (response) {
    console.log(response)
    return response
  },
  function (error) {
    console.log(error)
    if (error.response.status === 401) {
      user.logout()
    }
    return Promise.reject(error)
  }
)
</script>

<template>
  <div class="background" />
  <div class="fill-height">
    <RouterView />
  </div>
</template>

<style scoped>
.background {
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: -1000;
  position: fixed;
  height: 100vh;
  width: 100vw;
  filter: blur(2px) opacity(0.9);
  background: url('https://source.unsplash.com/random?orientation=landscape&collections=2281806')
    no-repeat center center;
  background-size: cover;
}
</style>
