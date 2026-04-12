<template>
  <div class="dashboard">
    <!-- Page Header -->
    <div class="page-header">
      <h2>Dashboard</h2>
      <el-date-picker
        v-model="selectedDate"
        type="date"
        value-format="YYYY-MM-DD"
        @change="loadData"
        class="date-picker"
      />
    </div>

    <!-- Search Bar -->
    <div class="search-section">
      <div class="search-bar">
        <el-input
          v-model="searchQuery"
          placeholder="Search activities, commits, worklogs..."
          size="large"
          @keyup.enter="doSearch"
          clearable
          @clear="searchResults = []"
          class="search-input"
        >
          <template #prefix>
            <el-icon :size="18" style="color: var(--text-tertiary)"><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="searchType" placeholder="All" style="width: 140px" clearable size="large">
          <el-option label="All" value="" />
          <el-option label="Activities" value="activity" />
          <el-option label="Git Commits" value="git_commit" />
          <el-option label="Worklogs" value="worklog" />
        </el-select>
        <el-button type="primary" @click="doSearch" :loading="searching" size="large" round>
          Search
        </el-button>
      </div>

      <!-- Search Results -->
      <div v-if="searchResults.length > 0" class="search-results">
        <el-table :data="searchResults" max-height="400">
          <el-table-column label="Type" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="sourceTagType(row.source_type)">{{ row.source_type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="text_content" label="Content" show-overflow-tooltip />
          <el-table-column label="Relevance" width="100">
            <template #default="{ row }">
              <span class="relevance-score">{{ row.distance !== undefined ? (1 - row.distance).toFixed(2) : '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div v-else-if="searchQuery && searched" class="search-empty">
        No results found
      </div>
    </div>

    <!-- Stats Row -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--warning); background: rgba(255, 159, 10, 0.1)">
          <el-icon :size="22"><Clock /></el-icon>
        </div>
        <div class="stat-value" style="color: var(--warning)">{{ dashboard.pending_review_count }}</div>
        <div class="stat-label">Pending Review</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--success); background: rgba(52, 199, 89, 0.1)">
          <el-icon :size="22"><CircleCheck /></el-icon>
        </div>
        <div class="stat-value" style="color: var(--success)">{{ dashboard.submitted_hours }}h</div>
        <div class="stat-label">Submitted Hours</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color: var(--accent); background: rgba(0, 113, 227, 0.1)">
          <el-icon :size="22"><DataLine /></el-icon>
        </div>
        <div class="stat-value" style="color: var(--accent)">{{ totalActivityHours }}h</div>
        <div class="stat-label">Total Activity</div>
      </div>
    </div>

    <!-- Activity Breakdown -->
    <div class="section">
      <h4 class="section-title">Activity Breakdown</h4>
      <div class="breakdown-list">
        <div v-for="item in dashboard.activity_summary" :key="item.category" class="breakdown-row">
          <div class="breakdown-info">
            <span class="breakdown-category">{{ item.category }}</span>
          </div>
          <div class="breakdown-bar-wrapper">
            <div class="breakdown-bar" :style="{ width: getBarWidth(item.total_sec) + '%' }"></div>
          </div>
          <span class="breakdown-hours">{{ (item.total_sec / 3600).toFixed(1) }}h</span>
        </div>
        <div v-if="!dashboard.activity_summary?.length" class="empty-state">
          No activity data for this date
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const selectedDate = ref(new Date().toISOString().split('T')[0])
const dashboard = ref({ pending_review_count: 0, submitted_hours: 0, activity_summary: [] })

const searchQuery = ref('')
const searchType = ref('')
const searchResults = ref([])
const searching = ref(false)
const searched = ref(false)

const totalActivityHours = computed(() => {
  const total = (dashboard.value.activity_summary || []).reduce((s, a) => s + a.total_sec, 0)
  return (total / 3600).toFixed(1)
})

function getBarWidth(sec) {
  const max = Math.max(...(dashboard.value.activity_summary || []).map(a => a.total_sec), 1)
  return (sec / max) * 100
}

function sourceTagType(type) {
  return { activity: 'success', git_commit: 'warning', worklog: 'info' }[type] || ''
}

async function loadData() {
  const res = await api.getDashboard(selectedDate.value)
  dashboard.value = res.data
}

async function doSearch() {
  if (!searchQuery.value.trim()) return
  searching.value = true
  searched.value = false
  try {
    const res = await api.search(searchQuery.value, 20, searchType.value || null)
    searchResults.value = res.data
  } catch (e) {
    ElMessage.warning(e.response?.data?.detail || 'Search unavailable')
    searchResults.value = []
  } finally {
    searching.value = false
    searched.value = true
  }
}

onMounted(loadData)
</script>

<style scoped>
.dashboard {
  max-width: 900px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.search-section {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 20px;
  margin-bottom: 24px;
}

.search-bar {
  display: flex;
  gap: 10px;
}

.search-input {
  flex: 1;
}

.search-results {
  margin-top: 20px;
  border-top: 1px solid var(--border);
  padding-top: 16px;
}

.search-empty {
  text-align: center;
  padding: 24px;
  color: var(--text-tertiary);
  font-size: 14px;
  margin-top: 16px;
}

.relevance-score {
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 24px;
  text-align: center;
  transition: all 0.2s ease;
}

.stat-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-1px);
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -1px;
  line-height: 1.1;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.section {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 24px;
}

.section-title {
  margin-bottom: 20px;
  font-size: 17px;
}

.breakdown-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.breakdown-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 0;
}

.breakdown-category {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  width: 100px;
  text-transform: capitalize;
}

.breakdown-bar-wrapper {
  flex: 1;
  height: 6px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 3px;
  overflow: hidden;
}

.breakdown-bar {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.4s ease;
  opacity: 0.7;
}

.breakdown-hours {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  width: 48px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.empty-state {
  text-align: center;
  padding: 32px;
  color: var(--text-tertiary);
  font-size: 14px;
}
</style>
