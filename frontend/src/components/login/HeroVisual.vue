<script setup lang="ts">
// The login page's picture: a few Tallied tiles, drawn in SVG with illustrative figures.
// Static on purpose: it must render before sign-in and never call the API.
const R = 34
const CIRC = 2 * Math.PI * R
</script>

<template>
  <div class="relative w-full max-w-[33rem] h-[20rem] select-none" aria-hidden="true">
    <!-- Net worth -->
    <div class="hero-card float-a absolute left-0 top-4 w-[19rem] p-4">
      <div class="flex items-baseline justify-between">
        <span class="text-[11px] uppercase tracking-wider text-indigo-200/80">Net worth</span>
        <span class="text-[11px] font-medium text-emerald-300">+$41,210 this year</span>
      </div>
      <div class="mt-1 text-2xl font-semibold tabular-nums text-white">$612,480</div>
      <svg viewBox="0 0 260 74" class="mt-2 w-full h-16 overflow-visible">
        <defs>
          <linearGradient id="nw-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#818cf8" stop-opacity="0.45" />
            <stop offset="100%" stop-color="#818cf8" stop-opacity="0" />
          </linearGradient>
        </defs>
        <path d="M0.0,56.2 L21.7,52.5 L43.3,58.8 L65.0,47.5 L86.7,41.2 L108.3,45.0 L130.0,33.8 L151.7,27.5 L173.3,31.2 L195.0,20.0 L216.7,12.5 L238.3,16.2 L260.0,5.0 L260,70 L0,70 Z" fill="url(#nw-fill)" />
        <path d="M0.0,56.2 L21.7,52.5 L43.3,58.8 L65.0,47.5 L86.7,41.2 L108.3,45.0 L130.0,33.8 L151.7,27.5 L173.3,31.2 L195.0,20.0 L216.7,12.5 L238.3,16.2 L260.0,5.0" fill="none" stroke="#a5b4fc" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" class="draw" pathLength="1" />
        <circle cx="260.0" cy="5.0" r="4" fill="#e0e7ff" />
      </svg>
    </div>

    <!-- Plan -->
    <div class="hero-card float-b absolute left-[20.5rem] top-0 w-[10.5rem] p-4 flex flex-col items-center text-center">
      <svg viewBox="0 0 80 80" class="w-20 h-20 -rotate-90">
        <circle cx="40" cy="40" :r="R" fill="none" stroke="rgba(255,255,255,0.12)" stroke-width="8" />
        <circle cx="40" cy="40" :r="R" fill="none" stroke="#34d399" stroke-width="8" stroke-linecap="round"
          :stroke-dasharray="CIRC" :stroke-dashoffset="CIRC * 0.09" class="ring" />
      </svg>
      <div class="-mt-[3.4rem] mb-6 text-lg font-semibold text-white tabular-nums">91%</div>
      <div class="text-[11px] leading-tight text-indigo-100/80">chance the plan lasts, retiring at 55</div>
    </div>

    <!-- Spending pace -->
    <div class="hero-card float-c absolute left-[13rem] bottom-0 w-[17rem] p-4">
      <div class="text-[11px] uppercase tracking-wider text-indigo-200/80">Spending this month</div>
      <div class="mt-0.5 text-sm text-white"><span class="font-semibold tabular-nums">$1,932</span>
        <span class="text-indigo-100/70">&nbsp;· $213 less than last month</span></div>
      <svg viewBox="0 0 220 66" class="mt-2 w-full h-14 overflow-visible">
        <path d="M0.0,62.9 L7.6,59.3 L15.2,57.7 L22.8,55.6 L30.3,54.2 L37.9,51.6 L45.5,50.0 L53.1,48.4 L60.7,47.7 L68.3,45.6 L75.9,41.9 L83.4,41.2 L91.0,40.2 L98.6,39.6 L106.2,35.9 L113.8,33.3 L121.4,31.7 L129.0,28.0 L136.6,27.0 L144.1,26.3 L151.7,22.6 L159.3,18.9 L166.9,17.8 L174.5,15.2 L182.1,11.5 L189.7,7.8 L197.2,7.3 L204.8,5.7 L212.4,5.2 L220.0,3.0" fill="none" stroke="rgba(255,255,255,0.28)" stroke-width="2" stroke-linejoin="round" />
        <path d="M0.0,63.2 L7.6,61.3 L15.2,60.5 L22.8,59.5 L30.3,56.8 L37.9,55.7 L45.5,53.0 L53.1,52.5 L60.7,49.9 L68.3,47.2 L75.9,46.4 L83.4,44.9 L91.0,43.3 L98.6,40.6 L106.2,39.1 L113.8,38.1 L121.4,36.1 L129.0,35.4 L136.6,32.7 L144.1,30.0 L144.1,64 L0,64 Z" fill="rgba(129,140,248,0.25)" />
        <path d="M0.0,63.2 L7.6,61.3 L15.2,60.5 L22.8,59.5 L30.3,56.8 L37.9,55.7 L45.5,53.0 L53.1,52.5 L60.7,49.9 L68.3,47.2 L75.9,46.4 L83.4,44.9 L91.0,43.3 L98.6,40.6 L106.2,39.1 L113.8,38.1 L121.4,36.1 L129.0,35.4 L136.6,32.7 L144.1,30.0" fill="none" stroke="#a5b4fc" stroke-width="2.5" stroke-linejoin="round" class="draw" pathLength="1" />
        <circle cx="144.1" cy="30.0" r="3.5" fill="#e0e7ff" />
      </svg>
    </div>

    <!-- RSU vest -->
    <div class="hero-card float-b absolute left-6 bottom-6 flex items-center gap-3 px-4 py-3">
      <span class="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-400/15 text-emerald-300 text-sm">◆</span>
      <div>
        <div class="text-sm font-medium text-white">RSU vest · 50 shares</div>
        <div class="text-[11px] text-indigo-100/70">Nov 15 · about $21,400</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hero-card {
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 20px 45px -20px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(10px);
}
.draw { stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 1.6s 0.2s ease-out forwards; }
.ring { transition: stroke-dashoffset 1.2s ease-out; }
.float-a { animation: float 7s ease-in-out infinite; }
.float-b { animation: float 8s ease-in-out -2s infinite; }
.float-c { animation: float 9s ease-in-out -4s infinite; }
@keyframes draw { to { stroke-dashoffset: 0; } }
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }
@media (prefers-reduced-motion: reduce) {
  .float-a, .float-b, .float-c { animation: none; }
  .draw { animation: none; stroke-dashoffset: 0; }
}
</style>
