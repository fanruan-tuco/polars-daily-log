<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px">
      <h2>Dashboard</h2>
      <el-date-picker v-model="selectedDate" type="date" value-format="YYYY-MM-DD" @change="loadData" />
    </div>

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
import api from '../api'

const selectedDate = ref(new Date().toISOString().split('T')[0])
const dashboard = ref({ pending_review_count: 0, submitted_hours: 0, activity_summary: [] })

const totalActivityHours = computed(() => {
  const total = (dashboard.value.activity_summary || []).reduce((s, a) => s + a.total_sec, 0)
  return (total / 3600).toFixed(1)
})

async function loadData() {
  const res = await api.getDashboard(selectedDate.value)
  dashboard.value = res.data
}

onMounted(loadData)
</script>
