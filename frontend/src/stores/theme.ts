import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Single source of truth for dark mode. App.vue toggles it; useChartDefaults,
 * the ERD canvas and the Scalar iframe read it, so charts re-theme when the
 * user flips the switch instead of caching the class list at mount.
 */
export const useThemeStore = defineStore('theme', () => {
  const dark = ref(false)

  function apply(value: boolean) {
    dark.value = value
    document.documentElement.classList.toggle('dark', value)
    try {
      localStorage.setItem('theme', value ? 'dark' : 'light')
    } catch {
      // private window or blocked storage: the choice just doesn't persist
    }
  }

  function init() {
    let saved: string | null = null
    try {
      saved = localStorage.getItem('theme')
    } catch {
      saved = null
    }
    dark.value = saved === 'dark'
    document.documentElement.classList.toggle('dark', dark.value)
  }

  function toggle() {
    apply(!dark.value)
  }

  return { dark, init, toggle, apply }
})
