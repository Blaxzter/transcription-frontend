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
  top: -4px;
  left: -4px;
  height: 101vh;
  width: 101vw;
  filter: blur(4px) opacity(0.9);
  background: url('https://picsum.photos/1920/1080?random') no-repeat center center;
  background-size: cover;
}
</style>
