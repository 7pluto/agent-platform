import { createApp } from 'vue'
import { createPinia } from 'pinia'
import RootApp from './RootApp.vue'
import { router } from './app/router'
import './styles.css'

createApp(RootApp).use(createPinia()).use(router).mount('#app')
