import { onBeforeUnmount, ref, type Ref } from 'vue'

/**
 * Reactive `window.matchMedia(query).matches`. Safe without a window (returns false).
 * Example: const isMobile = useMediaQuery('(max-width: 640px)')
 */
export function useMediaQuery(query: string): Ref<boolean> {
  const matches = ref(false)
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return matches

  const mql = window.matchMedia(query)
  matches.value = mql.matches
  const onChange = (e: MediaQueryListEvent) => { matches.value = e.matches }
  mql.addEventListener('change', onChange)
  // Works both inside components (cleanup on unmount) and outside (listener stays, harmless).
  try {
    onBeforeUnmount(() => mql.removeEventListener('change', onChange))
  } catch {
    /* called outside a component setup */
  }
  return matches
}
