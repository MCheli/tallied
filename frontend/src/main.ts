import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import { vDemoLock } from './directives/demoLock'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.directive('demo-lock', vDemoLock)
app.mount('#app')
