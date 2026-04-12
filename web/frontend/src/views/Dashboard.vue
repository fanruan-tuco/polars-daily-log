<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px">
      <h2>Dashboard</h2>
      <el-date-picker v-model="selectedDate" type="date" value-format="YYYY-MM-DD" @change="loadData" />
    </div>

    <!-- Search -->
    <el-card style="margin-bottom: 20px">
      <div style="display: flex; gap: 10px">
        <el-input
          v-model="searchQuery"
          placeholder="Search activities, commits, worklogs..."
          @keyup.enter="doSearch"
          clearable
          @clear="searchResults = []"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="searchType" placeholder="All" style="width: 150px" clearable>
          <el-option label="All" value="" />
          <el-option label="Activities" value="activity" />
          <el-option label="Git Commits" value="git_commit" />
          <el-option label="Worklogs" value="worklog" />
        </el-select>
        <el-button type="primary" @click="doSearch" :loading="searching">Search</el-button>
      </div>

      <div v-if="searchResults.length > 0" style="margin-top: 16px">
        <el-table :data="searchResults" stripe max-height="400">
          <el-table-column label="Type" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="sourceTagType(row.source_type)">{{ row.source_type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="text_content" label="Content" show-overflow-tooltip />
          <el-table-column label="Relevance" width="100">
            <template #default="{ row }">
              {{ row.distance !== undefined ? (1 - row.distance).toFixed(2) : '-' }}
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div v-else-if="searchQuery && searched" style="text-align: center; padding: 20px; color: #909399">
        No results
      </div>
    </el-card>

    <el-row :gutter="20" style="margin-bottom: 20px">
      <el-col :span="8">
        <el-card>
          <template #header>Pending Review</template>
          <div style="font-size: 36px; text-align: center; color: #E6A23C">
            {{ dashboard.pending_review_count }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>Submitted Hours</template>
          <div style="font-size: 36px; text-align: center; color: #67C23A">
            {{ dashboard.submitted_hours }}h
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>Total Activity</template>
          <div style="font-size: 36px; text-align: center; color: #409EFF">
            {{ totalActivityHours }}h
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card>
      <template #header>Activity Breakdown</template>
      <el-table :data="dashboard.activity_summary" stripe>
        <el-table-column prop="category" label="Category" />
        <el-table-column label="Duration">
          <template #default="{ row }">
            {{ (row.total_sec / 3600).toFixed(1) }}h
          </template>
        </el-table-column>
      </el-table>
    </el-card>
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
