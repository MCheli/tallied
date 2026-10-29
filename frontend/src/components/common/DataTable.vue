<script setup lang="ts">
/**
 * DataTable — every table on a page goes through this wrapper.
 *
 * It gives the table its own horizontal scroll container (so a wide table scrolls inside its
 * card instead of making the whole page scroll sideways on a phone), consistent header styling,
 * and an empty-state row.
 *
 * Usage:
 *   <DataTable :empty="rows.length === 0" empty-text="No transactions in this period" :columns="5">
 *     <thead><tr><th>Date</th>…</tr></thead>
 *     <tbody><tr v-for …>…</tr></tbody>
 *   </DataTable>
 *
 * Props: empty (boolean; when true the slot is replaced by one empty-state row), emptyText (default "No data"),
 *        columns (colspan for the empty row, default 1), dense (smaller cell padding), sticky (sticky thead).
 * Slot (default): your own <thead> and <tbody>. Header cells pick up the uppercase 11px style automatically.
 */
withDefaults(defineProps<{
  empty?: boolean
  emptyText?: string
  columns?: number
  dense?: boolean
  sticky?: boolean
}>(), {
  empty: false,
  emptyText: 'No data',
  columns: 1,
  dense: false,
  sticky: false,
})
</script>

<template>
  <div class="data-table overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 min-w-0" :class="{ 'data-table--dense': dense, 'data-table--sticky': sticky }">
    <table class="min-w-full text-sm text-left text-gray-700 dark:text-gray-300">
      <slot v-if="!empty" />
      <tbody v-else>
        <tr>
          <td :colspan="columns" class="py-10 text-center text-sm text-gray-400 dark:text-gray-500">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.data-table :deep(thead th) {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #6b7280;
  padding: 0.5rem 0.75rem;
  white-space: nowrap;
  border-bottom: 1px solid #e5e7eb;
  background: inherit;
}
:global(.dark) .data-table :deep(thead th) {
  color: #9ca3af;
  border-bottom-color: #1f2937;
}
.data-table :deep(tbody td) {
  padding: 0.625rem 0.75rem;
  border-bottom: 1px solid #f3f4f6;
  vertical-align: middle;
}
:global(.dark) .data-table :deep(tbody td) {
  border-bottom-color: #111827;
}
.data-table :deep(tbody tr:last-child td) {
  border-bottom: 0;
}
.data-table--dense :deep(tbody td) {
  padding: 0.375rem 0.625rem;
}
.data-table--sticky :deep(thead th) {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #fff;
}
:global(.dark) .data-table--sticky :deep(thead th) {
  background: #111827;
}
</style>
