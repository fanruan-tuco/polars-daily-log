<template>
  <div class="activities-page">
    <div class="page-header">
      <h2>Activities</h2>
    </div>

    <div class="activities-layout">
      <!-- Left: Date List -->
      <div class="dates-panel">
        <div class="dates-header">
          <span class="dates-title">Dates</span>
          <el-button size="small" text @click="loadDates" class="refresh-btn">
            <el-icon><Refresh /></el-icon>
          </el-button>
        </div>
        <div v-if="dates.length === 0" class="dates-empty">
          Nothing recorded yet
        </div>
        <div class="dates-list">
          <div
            v-for="d in dates" :key="d.date"
            @click="selectDate(d.date)"
            :class="['date-item', { active: d.date === selectedDate }]"
          >
            <div class="date-label">{{ d.date }}</div>
            <div class="date-meta">
              {{ d.count }} records &middot; {{ (d.total_sec / 3600).toFixed(1) }}h
            </div>
          </div>
        </div>
      </div>

      <!-- Right: Activity Detail -->
      <div class="detail-panel">
        <div v-if="selectedDate" class="detail-content">
          <div class="detail-header">
            <div class="detail-header-info">
              <span class="detail-date">{{ selectedDate }}</span>
              <span class="detail-stats">{{ activities.length }} records &middot; {{ totalHours }}h</span>
            </div>
            <div class="detail-actions">
              <el-button
                size="small"
                round
                @click="viewMode = viewMode === 'table' ? 'timeline' : 'table'"
              >
                {{ viewMode === 'table' ? 'Timeline' : 'Table' }}
              </el-button>
              <el-popconfirm
                title="Delete all records for this date?"
                confirm-button-text="Delete"
                cancel-button-text="Cancel"
                @confirm="deleteAllForDate"
              >
                <template #reference>
                  <el-button size="small" type="danger" round>Delete All</el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>

          <!-- Table View -->
          <div v-if="viewMode === 'table'" class="table-wrapper">
            <el-table :data="activities" style="width: 100%" max-height="600">
              <el-table-column label="Time" width="90">
                <template #default="{ row }">
                  <span class="time-cell">{{ formatTime(row.timestamp) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="Category" width="120">
                <template #default="{ row }">
                  <el-tag :type="categoryType(row.category)" size="small">{{ row.category }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="app_name" label="App" width="150" show-overflow-tooltip />
              <el-table-column prop="window_title" label="Title" show-overflow-tooltip />
              <el-table-column label="Duration" width="80">
                <template #default="{ row }">
                  <span class="duration-cell">{{ formatDuration(row.duration_sec) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="OCR" width="60">
                <template #default="{ row }">
                  <el-button v-if="getOcrText(row)" size="small" text @click="showOcr(row)">
                    <el-icon><View /></el-icon>
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column label="" width="60">
                <template #default="{ row }">
                  <el-popconfirm title="Delete?" @confirm="deleteOne(row.id)">
                    <template #reference>
                      <el-button size="small" text type="danger">
                        <el-icon><Delete /></el-icon>
                      </el-button>
                    </template>
                  </el-popconfirm>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- Timeline View -->
          <div v-else class="timeline-wrapper">
            <el-timeline>
              <el-timeline-item
                v-for="row in activities" :key="row.id"
                :timestamp="formatTime(row.timestamp)"
                placement="top"
              >
                <div class="timeline-card">
                  <div class="timeline-card-main">
                    <div class="timeline-card-left">
                      <el-tag :type="categoryType(row.category)" size="small">{{ row.category }}</el-tag>
                      <strong>{{ row.app_name }}</strong>
                      <span class="timeline-title">{{ row.window_title }}</span>
                    </div>
                    <div class="timeline-card-right">
                      <span class="timeline-duration">{{ formatDuration(row.duration_sec) }}</span>
                      <el-button v-if="getOcrText(row)" size="small" text @click="showOcr(row)">
                        <el-icon><View /></el-icon>
                      </el-button>
                      <el-popconfirm title="Delete?" @confirm="deleteOne(row.id)">
                        <template #reference>
                          <el-button size="small" text type="danger">
                            <el-icon><Delete /></el-icon>
                          </el-button>
                        </template>
                      </el-popconfirm>
                    </div>
                  </div>
                  <div v-if="row.url" class="timeline-url">{{ row.url }}</div>
                </div>
              </el-timeline-item>
            </el-timeline>
          </div>

          <div v-if="activities.length === 0" class="empty-state">
            No records for this date
          </div>
        </div>

        <div v-else class="empty-state-large">
          <el-icon :size="48" color="var(--text-tertiary)"><Monitor /></el-icon>
          <p>Select a date to view activities</p>
        </div>
      </div>
    </div>

    <!-- OCR Dialog -->
    <el-dialog v-model="ocrVisible" title="OCR Content" width="600px">
      <pre class="ocr-content">{{ ocrContent }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const dates = ref([])
const selectedDate = ref(null)
const activities = ref([])
const viewMode = ref('table')
const ocrVisible = ref(false)
const ocrContent = ref('')

const totalHours = computed(() => {
  const sec = activities.value.reduce((s, a) => s + (a.duration_sec || 0), 0)
  return (sec / 3600).toFixed(1)
})

async function loadDates() {
  const res = await api.getActivityDates()
  dates.value = res.data
  if (dates.value.length > 0 && !selectedDate.value) {
    selectDate(dates.value[0].date)
  }
}

async function selectDate(d) {
  selectedDate.value = d
  const res = await api.getActivities(d)
  activities.value = res.data
}

async function deleteOne(id) {
  await api.deleteActivity(id)
  ElMessage.success('Deleted')
  await selectDate(selectedDate.value)
  await loadDates()
}

async function deleteAllForDate() {
  await api.deleteActivitiesByDate(selectedDate.value)
  ElMessage.success(`All records for ${selectedDate.value} deleted`)
  selectedDate.value = null
  activities.value = []
  await loadDates()
}

function formatTime(ts) {
  if (!ts) return ''
  return ts.substring(11, 19)
}

function formatDuration(sec) {
  if (!sec) return '0s'
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.round(sec / 60)}m`
  return `${(sec / 3600).toFixed(1)}h`
}

function categoryType(cat) {
  const map = {
    coding: 'success', meeting: 'danger', communication: 'warning',
    design: '', writing: 'info', research: '', reading: 'info',
    browsing: '', other: 'info',
  }
  return map[cat] || ''
}

function getOcrText(row) {
  if (!row.signals) return null
  try {
    const signals = typeof row.signals === 'string' ? JSON.parse(row.signals) : row.signals
    return signals.ocr_text || null
  } catch { return null }
}

function showOcr(row) {
  ocrContent.value = getOcrText(row) || 'No OCR content'
  ocrVisible.value = true
}

onMounted(loadDates)
</script>

<style scoped>
.activities-page {
  max-width: 1100px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.activities-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 24px;
  align-items: start;
}

.dates-panel {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}

.dates-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.dates-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.refresh-btn {
  color: var(--text-tertiary) !important;
}

.dates-empty {
  color: var(--text-tertiary);
  text-align: center;
  padding: 32px 20px;
  font-size: 14px;
}

.dates-list {
  padding: 8px;
  max-height: 600px;
  overflow-y: auto;
}

.date-item {
  padding: 12px 14px;
  cursor: pointer;
  border-radius: 10px;
  margin-bottom: 2px;
  transition: all 0.2s ease;
}

.date-item:hover {
  background: rgba(0, 0, 0, 0.03);
}

.date-item.active {
  background: rgba(0, 113, 227, 0.08);
}

.date-label {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.date-item.active .date-label {
  color: var(--accent);
}

.date-meta {
  font-size: 12px;
  color: var(--text-tertiary);
}

.detail-panel {
  min-height: 400px;
}

.detail-content {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.detail-header-info {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.detail-date {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
}

.detail-stats {
  font-size: 13px;
  color: var(--text-secondary);
}

.detail-actions {
  display: flex;
  gap: 8px;
}

.table-wrapper {
  padding: 0;
}

.time-cell {
  font-variant-numeric: tabular-nums;
  font-size: 13px;
  color: var(--text-secondary);
}

.duration-cell {
  font-variant-numeric: tabular-nums;
  font-size: 13px;
  color: var(--text-secondary);
}

.timeline-wrapper {
  padding: 20px;
}

.timeline-card {
  background: var(--surface-hover);
  border-radius: 12px;
  padding: 12px 16px;
}

.timeline-card-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.timeline-card-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.timeline-card-left strong {
  font-size: 14px;
}

.timeline-title {
  color: var(--text-secondary);
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline-card-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.timeline-duration {
  font-size: 13px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}

.timeline-url {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 6px;
  word-break: break-all;
}

.empty-state {
  text-align: center;
  padding: 48px;
  color: var(--text-tertiary);
  font-size: 14px;
}

.empty-state-large {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 40px;
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

.empty-state-large p {
  color: var(--text-tertiary);
  font-size: 15px;
  margin-top: 12px;
}

.ocr-content {
  white-space: pre-wrap;
  font-size: 13px;
  max-height: 400px;
  overflow: auto;
  background: var(--bg);
  padding: 16px;
  border-radius: var(--radius-sm);
  font-family: "SF Mono", Menlo, Monaco, monospace;
  line-height: 1.5;
}
</style>
