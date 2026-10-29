<script setup lang="ts">
/**
 * InfoTooltip — the "what is this number" affordance on every tile.
 *
 * Opens on hover and keyboard focus, and on tap (click toggles; tapping outside or Escape closes),
 * so it works on phones. Never wider than the viewport.
 *
 * Props: text (HTML string; keep it to what the tile shows and what feeds it).
 */
import { nextTick, onBeforeUnmount, ref } from 'vue'

defineProps<{ text: string }>()

const show = ref(false)
const tooltipStyle = ref<Record<string, string>>({})
const iconRef = ref<HTMLElement | null>(null)
const tipRef = ref<HTMLElement | null>(null)
let openedByTap = false

function place() {
  const icon = iconRef.value
  if (!icon) return
  const rect = icon.getBoundingClientRect()
  const margin = 12
  const vw = window.innerWidth
  const width = Math.min(340, vw - margin * 2)
  const height = Math.min(300, tipRef.value?.offsetHeight || 220)

  let left = rect.left + rect.width / 2 - width / 2
  left = Math.max(margin, Math.min(left, vw - width - margin))

  const style: Record<string, string> = { position: 'fixed', width: `${width}px`, left: `${left}px` }
  if (rect.bottom + 8 + height > window.innerHeight - margin && rect.top > height + margin) {
    style.bottom = `${window.innerHeight - rect.top + 8}px`
    style.top = 'auto'
  } else {
    style.top = `${rect.bottom + 8}px`
  }
  tooltipStyle.value = style
}

function open(viaTap = false) {
  openedByTap = viaTap || openedByTap
  show.value = true
  place()
  nextTick(place)
  document.addEventListener('keydown', onKey)
  document.addEventListener('pointerdown', onOutside, true)
}

function close() {
  show.value = false
  openedByTap = false
  document.removeEventListener('keydown', onKey)
  document.removeEventListener('pointerdown', onOutside, true)
}

function onToggle(e: Event) {
  e.stopPropagation()
  if (show.value && openedByTap) close()
  else open(true)
}

function onLeave() {
  // Hover closes; a tap-opened tooltip stays until tapped away.
  if (!openedByTap) close()
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}

function onOutside(e: Event) {
  const t = e.target as Node
  if (iconRef.value?.contains(t) || tipRef.value?.contains(t)) return
  close()
}

onBeforeUnmount(close)
</script>

<template>
  <span class="info-tooltip-wrapper" @mouseenter="open(false)" @mouseleave="onLeave">
    <button
      ref="iconRef"
      type="button"
      class="info-tooltip-icon"
      :aria-expanded="show"
      aria-label="More information"
      @click="onToggle"
      @focus="open(false)"
      @blur="onLeave"
    >
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5">
        <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clip-rule="evenodd" />
      </svg>
    </button>
    <Teleport to="body">
      <div v-if="show" ref="tipRef" class="info-tooltip-content" role="tooltip" :style="tooltipStyle" v-html="text"></div>
    </Teleport>
  </span>
</template>

<style scoped>
.info-tooltip-wrapper {
  display: inline-flex;
  align-items: center;
  margin-left: 2px;
  vertical-align: middle;
}

.info-tooltip-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  /* 24px visual box, padded to a comfortable tap target without pushing text apart */
  min-width: 24px;
  min-height: 24px;
  padding: 5px;
  margin: -5px 0;
  border: 0;
  background: transparent;
  color: #9ca3af;
  cursor: help;
  border-radius: 9999px;
  transition: color 0.15s;
  outline: none;
  -webkit-tap-highlight-color: transparent;
}

.info-tooltip-icon:hover,
.info-tooltip-icon:focus-visible,
.info-tooltip-icon[aria-expanded="true"] {
  color: #6366f1;
}
</style>

<style>
.info-tooltip-content {
  padding: 12px 14px;
  background: #1f2937;
  color: #e5e7eb;
  font-size: 11px;
  line-height: 1.6;
  border-radius: 8px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
  z-index: 9999;
  max-height: 300px;
  overflow-y: auto;
  overflow-wrap: anywhere;
}

.info-tooltip-content strong {
  color: #f9fafb;
  font-weight: 600;
}

.info-tooltip-content code {
  background: #374151;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 10px;
}
</style>
