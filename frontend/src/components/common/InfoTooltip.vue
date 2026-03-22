<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  text: string
}>()

const show = ref(false)
const tooltipStyle = ref<Record<string, string>>({})
const iconRef = ref<HTMLElement | null>(null)

function onEnter() {
  show.value = true
  if (!iconRef.value) return

  const rect = iconRef.value.getBoundingClientRect()
  const tooltipWidth = 340
  const tooltipHeight = 250 // estimated max
  const margin = 12

  // Default: show below the icon
  let top = rect.bottom + 8
  let left = rect.left + rect.width / 2 - tooltipWidth / 2

  // If would go off the bottom, show above instead
  if (top + tooltipHeight > window.innerHeight - margin) {
    top = rect.top - 8 // will use transform to move up
    tooltipStyle.value = {
      position: 'fixed',
      width: `${tooltipWidth}px`,
      left: `${Math.max(margin, Math.min(left, window.innerWidth - tooltipWidth - margin))}px`,
      bottom: `${window.innerHeight - rect.top + 8}px`,
      top: 'auto',
    }
    return
  }

  // Clamp left edge
  left = Math.max(margin, Math.min(left, window.innerWidth - tooltipWidth - margin))

  tooltipStyle.value = {
    position: 'fixed',
    width: `${tooltipWidth}px`,
    top: `${top}px`,
    left: `${left}px`,
  }
}

function onLeave() {
  show.value = false
}
</script>

<template>
  <span class="info-tooltip-wrapper" @mouseenter="onEnter" @mouseleave="onLeave" @focus="onEnter" @blur="onLeave">
    <span ref="iconRef" class="info-tooltip-icon" tabindex="0">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5">
        <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clip-rule="evenodd" />
      </svg>
    </span>
    <Teleport to="body">
      <div v-if="show" class="info-tooltip-content" :style="tooltipStyle" v-html="text"></div>
    </Teleport>
  </span>
</template>

<style scoped>
.info-tooltip-wrapper {
  display: inline-flex;
  align-items: center;
  margin-left: 4px;
}

.info-tooltip-icon {
  display: inline-flex;
  align-items: center;
  color: #9ca3af;
  cursor: help;
  transition: color 0.15s;
  outline: none;
}

.info-tooltip-icon:hover,
.info-tooltip-icon:focus {
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
