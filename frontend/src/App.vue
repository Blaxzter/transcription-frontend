<script setup>
import { RouterView } from 'vue-router'
import { useUserStore } from '@/stores/user'
import {onMounted} from "vue";

const user = useUserStore()

onMounted(() => {
    user.auto_login()
})

</script>

<template>
    <div class="background"/>
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
    background: url('https://source.unsplash.com/random?orientation=landscape&collections=2281806') no-repeat center center;
    background-size: cover;
}


</style>
