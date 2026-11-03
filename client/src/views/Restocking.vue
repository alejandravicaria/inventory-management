<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.subtitle') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <div class="budget-top">
          <label for="budget-slider" class="budget-label">{{ t('restocking.budgetLabel') }}</label>
          <span class="budget-value">{{ money(budget) }}</span>
        </div>
        <input
          id="budget-slider"
          v-model.number="budget"
          class="budget-slider"
          type="range"
          min="0"
          :max="maxBudget"
          step="500"
        />
        <div class="budget-scale">
          <span>{{ money(0) }}</span>
          <span>{{ money(maxBudget) }}</span>
        </div>
      </div>

      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">{{ t('restocking.spent') }}</div>
          <div class="summary-value">{{ money(totalSpent) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">{{ t('restocking.remaining') }}</div>
          <div class="summary-value">{{ money(remaining) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">{{ t('restocking.itemsCount') }}</div>
          <div class="summary-value">{{ recommended.length }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">{{ t('restocking.leadTime') }}</div>
          <div class="summary-value">{{ recommended.length ? t('restocking.daysUnit', { count: orderLeadTime }) : '-' }}</div>
        </div>
      </div>

      <div v-if="orderResult" class="confirmation" role="status">
        <h3>{{ t('restocking.confirmation.title') }}</h3>
        <div class="confirmation-grid">
          <div><span class="summary-label">{{ t('restocking.confirmation.orderId') }}</span><strong>{{ orderResult.id }}</strong></div>
          <div><span class="summary-label">{{ t('restocking.confirmation.total') }}</span><strong>{{ money(orderResult.total_cost) }}</strong></div>
          <div><span class="summary-label">{{ t('restocking.confirmation.leadTime') }}</span><strong>{{ t('restocking.daysUnit', { count: orderResult.lead_time_days }) }}</strong></div>
          <div><span class="summary-label">{{ t('restocking.confirmation.expectedDelivery') }}</span><strong>{{ formatDate(orderResult.expected_delivery_date) }}</strong></div>
        </div>
        <router-link to="/orders" class="orders-link">{{ t('restocking.confirmation.viewOrders') }}</router-link>
      </div>

      <div v-if="submitError" class="error" role="alert">{{ submitError }}</div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }} ({{ recommended.length }})</h3>
          <button
            type="button"
            class="place-order"
            :disabled="recommended.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="recommended.length === 0" class="empty">{{ t('restocking.emptyState') }}</div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.name') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th class="num">{{ t('restocking.table.quantity') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.lineTotal') }}</th>
                <th>{{ t('restocking.table.supplier') }}</th>
                <th class="num">{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommended" :key="item.item_sku">
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ item.item_name }}</td>
                <td><span :class="['badge', item.trend]">{{ trendLabel(item.trend) }}</span></td>
                <td class="num">{{ item.quantity }}</td>
                <td class="num">{{ money(item.unit_cost, 2) }}</td>
                <td class="num"><strong>{{ money(item.line_total, 2) }}</strong></td>
                <td>{{ item.supplier_name }}</td>
                <td class="num">{{ t('restocking.daysUnit', { count: item.lead_time_days }) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'
import { recommendRestock, getMaxBudget } from '../utils/restockRecommendation'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const catalog = ref([])
    // Budget is always held in USD; only the display is converted for JPY
    const budget = ref(0)

    const submitting = ref(false)
    const submitError = ref(null)
    const orderResult = ref(null)

    const maxBudget = computed(() => getMaxBudget(catalog.value))
    const recommended = computed(() => recommendRestock(catalog.value, budget.value))
    const totalSpent = computed(() => recommended.value.reduce((sum, r) => sum + r.line_total, 0))
    const remaining = computed(() => Math.max(0, budget.value - totalSpent.value))
    // Order ships when its slowest item arrives, so lead time is the max across items
    const orderLeadTime = computed(() => Math.max(0, ...recommended.value.map(r => r.lead_time_days)))

    const money = (amount, decimals = 0) => {
      return decimals > 0
        ? formatCurrencyWithDecimals(amount, currentCurrency.value, decimals)
        : formatCurrency(amount, currentCurrency.value)
    }

    const trendLabel = (trend) => t(`trends.${trend}`)

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return '-'
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return date.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' })
    }

    const loadCatalog = async () => {
      try {
        loading.value = true
        error.value = null
        catalog.value = await api.getRestockCatalog()
        // Default to about half the max, snapped to the 500 step
        budget.value = Math.round(maxBudget.value / 2 / 500) * 500
      } catch (err) {
        error.value = t('restocking.loadError')
        console.error('Load error:', err)
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      if (recommended.value.length === 0 || submitting.value) return
      try {
        submitting.value = true
        submitError.value = null
        orderResult.value = await api.createRestockOrder({
          items: recommended.value.map(r => ({ item_sku: r.item_sku, quantity: r.quantity })),
          budget: budget.value
        })
      } catch (err) {
        // Prefer the backend's explanation (e.g. over budget, unknown SKU)
        submitError.value = err.response?.data?.detail
          ? String(err.response.data.detail)
          : t('restocking.submitError')
        console.error('Submit error:', err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadCatalog)

    return {
      t,
      loading,
      error,
      budget,
      maxBudget,
      recommended,
      totalSpent,
      remaining,
      orderLeadTime,
      submitting,
      submitError,
      orderResult,
      money,
      trendLabel,
      formatDate,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 1rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.budget-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.813rem;
  color: #64748b;
}

/* Range input styled to the slate palette (track + thumb for WebKit and Firefox) */
.budget-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  background: #e2e8f0;
  border-radius: 3px;
  outline: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #0f172a;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.4);
}

.budget-slider::-moz-range-track {
  height: 6px;
  background: #e2e8f0;
  border-radius: 3px;
}

.budget-slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #0f172a;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.4);
}

.budget-slider:focus-visible {
  outline: 2px solid #64748b;
  outline-offset: 4px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.summary-item {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
}

.summary-label {
  display: block;
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  margin-bottom: 0.25rem;
}

.summary-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.confirmation {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
  color: #065f46;
}

.confirmation h3 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
}

.confirmation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.confirmation-grid strong {
  display: block;
  color: #0f172a;
}

.orders-link {
  color: #1e40af;
  font-weight: 600;
  text-decoration: none;
}

.orders-link:hover {
  text-decoration: underline;
}

.place-order {
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
}

.place-order:hover:not(:disabled) {
  background: #1e293b;
}

.place-order:disabled {
  background: #cbd5e1;
  color: #64748b;
  cursor: not-allowed;
}

.empty {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.num {
  text-align: right;
}
</style>
