import { ref } from 'vue'

export type DataContext = 'spending' | 'income' | 'cash' | 'rsu' | 'retirement' | 'property' | 'assets'

/** Tables relevant to each page */
export const PAGE_TABLES: Record<DataContext, string[]> = {
  spending: ['transactions', 'accounts'],
  income: ['w2_records'],
  cash: ['accounts', 'balance_snapshots'],
  rsu: ['rsu_grants', 'vest_events', 'stock_prices'],
  retirement: ['retirement_accounts', 'retirement_snapshots', 'retirement_holdings'],
  property: ['mortgages', 'property_valuations', 'property_value_histories'],
  assets: ['vehicles', 'asset_value_histories'],
}

const isOpen = ref(false)
const context = ref<DataContext>('spending')

export function useDataExplorer() {
  function openData(ctx: DataContext) {
    context.value = ctx
    isOpen.value = true
  }

  function closeData() {
    isOpen.value = false
  }

  return { isOpen, context, openData, closeData }
}
