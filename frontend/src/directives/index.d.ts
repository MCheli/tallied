import type { vDemoLock } from './demoLock'

declare module 'vue' {
  interface GlobalDirectives {
    vDemoLock: typeof vDemoLock
  }
}
export {}
