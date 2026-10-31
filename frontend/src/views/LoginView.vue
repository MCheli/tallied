<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Database, FileText, LineChart, Landmark } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import { useAppConfig } from '../stores/appConfig'
import HeroVisual from '../components/login/HeroVisual.vue'

const API = import.meta.env.VITE_API_URL || ''
const auth = useAuthStore()
const appConfig = useAppConfig()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const configLoaded = ref(false)

const devMode = computed(() => appConfig.config?.dev_mode ?? false)
const googleSso = computed(() => appConfig.config?.google_sso ?? false)
const demoMode = computed(() => appConfig.demo)
const demoUrl = computed(() => appConfig.config?.demo_url ?? null)

const features = [
  { icon: Landmark, label: 'Bank sync' },
  { icon: FileText, label: 'AI document import' },
  { icon: LineChart, label: 'Monte Carlo retirement plan' },
  { icon: Database, label: 'SQL and API access' },
]

onMounted(async () => {
  await auth.checkAuth()
  if (auth.authenticated) {
    router.push('/')
    return
  }
  await appConfig.load()  // no config: the panel says no sign-in method is configured
  configLoaded.value = true
})

async function handleDevLogin() {
  error.value = ''
  loading.value = true
  const err = await auth.login(email.value, password.value)
  loading.value = false
  if (err) error.value = err
  else router.push('/')
}

async function enterDemo() {
  error.value = ''
  loading.value = true
  const err = await auth.demoLogin()
  loading.value = false
  if (err) error.value = err
  else router.push('/')
}

function handleGoogleLogin() {
  window.location.href = `${API}/api/v1/auth/google/login`
}
</script>

<template>
  <div class="min-h-dvh grid lg:grid-cols-[minmax(0,1.25fr)_minmax(24rem,1fr)] bg-white dark:bg-gray-950">
    <!-- Hero: always dark, the product at a glance -->
    <section class="hero relative overflow-hidden text-white px-6 sm:px-10 lg:px-14 pt-8 pb-10 lg:py-12 flex flex-col">
      <div class="relative z-10 flex items-center gap-2.5">
        <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/20 font-bold text-lg">T</span>
        <span class="text-xl font-bold tracking-tight">Tallied</span>
      </div>

      <div class="relative z-10 flex-1 flex flex-col justify-center gap-8 lg:gap-10 mt-8 lg:mt-12 max-w-2xl">
        <div>
          <h1 class="text-3xl sm:text-4xl lg:text-[2.75rem] font-semibold leading-[1.1] tracking-tight [text-wrap:balance]">
            Every account, paycheck, vest and plan, in one place you own.
          </h1>
          <p class="mt-4 text-base sm:text-lg text-indigo-100/80 max-w-xl leading-relaxed">
            A self-hosted household finance dashboard: spending, income, RSUs, 401(k), home equity and a
            retirement plan, all from one Postgres database you can query yourself.
          </p>
        </div>

        <HeroVisual class="hidden sm:block" />

        <ul class="hidden sm:flex flex-wrap gap-2">
          <li v-for="f in features" :key="f.label"
            class="inline-flex items-center gap-1.5 rounded-full bg-white/8 ring-1 ring-white/15 px-3 py-1 text-xs sm:text-sm text-indigo-50">
            <component :is="f.icon" class="w-3.5 h-3.5 text-indigo-300" />{{ f.label }}
          </li>
        </ul>
      </div>
    </section>

    <!-- Sign in -->
    <section class="flex flex-col justify-center px-6 sm:px-10 py-12 lg:py-14">
      <div class="w-full max-w-sm mx-auto">
        <div v-if="!configLoaded" class="flex justify-center py-8">
          <div class="h-6 w-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
        </div>

        <!-- The public demo deployment -->
        <template v-else-if="demoMode">
          <span class="inline-flex items-center rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 px-2.5 py-0.5 text-xs font-medium">Live demo</span>
          <h2 class="mt-3 text-2xl font-semibold text-gray-900 dark:text-white">Look around Tallied</h2>
          <p class="mt-2 text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
            You'll see the finances of <strong class="text-gray-800 dark:text-gray-200">Claudius Banks</strong>, a made-up
            software engineer. Every account, transaction and number is generated and rebuilt each night.
            Every page works; nothing can be changed or saved.
          </p>
          <button type="button" data-testid="enter-demo" :disabled="loading" @click="enterDemo"
            class="mt-6 w-full inline-flex items-center justify-center gap-2 py-3 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
            {{ loading ? 'Opening…' : 'Enter the demo' }} <ArrowRight class="w-4 h-4" />
          </button>
          <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">No sign-up, no email, nothing to install.</p>
          <div v-if="error" role="alert" class="mt-4 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-2">{{ error }}</div>
        </template>

        <template v-else>
          <h2 class="text-2xl font-semibold text-gray-900 dark:text-white">Sign in</h2>
          <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">Your finances, tallied.</p>

          <button v-if="googleSso" type="button" @click="handleGoogleLogin"
            class="mt-6 w-full flex items-center justify-center gap-3 py-2.5 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
            <svg class="w-5 h-5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Sign in with Google
          </button>

          <div v-if="googleSso && devMode" class="flex items-center gap-3 my-6">
            <div class="flex-1 h-px bg-gray-200 dark:bg-gray-700"></div>
            <span class="text-xs text-gray-400">or</span>
            <div class="flex-1 h-px bg-gray-200 dark:bg-gray-700"></div>
          </div>

          <form v-if="devMode" @submit.prevent="handleDevLogin" class="space-y-4" :class="{ 'mt-6': !googleSso }">
            <div>
              <label for="login-email" class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
              <input id="login-email" v-model="email" type="email" required autofocus
                class="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="claudius@tallied.dev" />
            </div>
            <div>
              <label for="login-password" class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
              <input id="login-password" v-model="password" type="password" required
                class="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="••••••" />
            </div>
            <div v-if="error" class="text-xs text-red-500 bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-2">{{ error }}</div>
            <button type="submit" :disabled="loading"
              class="w-full py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
              {{ loading ? 'Signing in...' : 'Sign in' }}
            </button>
            <p class="text-[10px] text-gray-400 text-center">Dev mode · local email/password sign-in is enabled (see backend/.env)</p>
          </form>

          <p v-if="!devMode && !googleSso" class="mt-6 text-sm text-gray-500">No authentication methods configured.</p>

          <a v-if="demoUrl" :href="demoUrl" data-testid="demo-link"
            class="group mt-8 block rounded-xl border border-indigo-100 dark:border-indigo-900/60 bg-indigo-50/60 dark:bg-indigo-950/30 p-4 hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors">
            <div class="flex items-center justify-between gap-3">
              <span class="text-sm font-semibold text-gray-900 dark:text-white">Just looking? Try the live demo</span>
              <ArrowRight class="w-4 h-4 text-indigo-600 dark:text-indigo-400 transition-transform group-hover:translate-x-0.5" />
            </div>
            <p class="mt-1 text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
              Every page, filled with the finances of Claudius Banks, a made-up household. Read-only, no sign-in.
            </p>
          </a>
        </template>

        <p class="mt-10 text-xs text-gray-400 dark:text-gray-500">
          Built by <a href="https://www.markcheli.com" class="underline underline-offset-2 hover:text-gray-600 dark:hover:text-gray-300">Mark Cheli</a>
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.hero {
  background:
    radial-gradient(60rem 30rem at 85% 10%, rgba(99, 102, 241, 0.35), transparent 60%),
    radial-gradient(40rem 30rem at 0% 100%, rgba(16, 185, 129, 0.16), transparent 60%),
    linear-gradient(160deg, #0b1023 0%, #111735 55%, #0d1430 100%);
}
.hero::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(ellipse at 60% 40%, black 30%, transparent 75%);
}
</style>
