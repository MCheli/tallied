import { ref } from 'vue'

export type ImportContext = 'income' | 'retirement' | 'property' | 'rsu' | 'general'

const isOpen = ref(false)
const context = ref<ImportContext>('general')
const onComplete = ref<(() => void) | null>(null)

export function useImportModal() {
  function openImport(opts: { context?: ImportContext; onComplete?: () => void } = {}) {
    context.value = opts.context || 'general'
    onComplete.value = opts.onComplete || null
    isOpen.value = true
  }

  function closeImport() {
    isOpen.value = false
    if (onComplete.value) {
      onComplete.value()
      onComplete.value = null
    }
  }

  return { isOpen, context, openImport, closeImport }
}
