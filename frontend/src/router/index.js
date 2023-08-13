import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import { useUserStore } from '@/stores/user'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { requiresAuth: true }
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/transcription/:transcription_id',
      name: 'transcription',
      component: () => import('../views/TranscriptionView.vue'),
      meta: { requiresAuth: true }
    }
  ]
})

router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  if (to.matched.some((record) => record.meta['requiresAuth'])) {
    console.log('requiresAuth', userStore.is_logged_in)
    if (userStore.is_logged_in) {
      next()
      return
    }
    next('/login')
  } else {
    next()
  }
})

export default router
