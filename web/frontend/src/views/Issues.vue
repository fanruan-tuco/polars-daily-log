<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px">
      <h2>Jira Issues</h2>
      <el-button type="primary" @click="dialogVisible = true">Add Issue</el-button>
    </div>

    <el-table :data="issues" stripe>
      <el-table-column prop="issue_key" label="Key" width="150" />
      <el-table-column prop="summary" label="Summary" />
      <el-table-column label="Active" width="100">
        <template #default="{ row }">
          <el-switch v-model="row.is_active" @change="toggleActive(row)" />
        </template>
      </el-table-column>
      <el-table-column label="Actions" width="120">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="deleteIssue(row.issue_key)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="Add Jira Issue" width="500px">
      <el-form :model="newIssue" label-width="120px">
        <el-form-item label="Issue Key" required>
          <el-input v-model="newIssue.issue_key" placeholder="e.g. PROJ-101" />
        </el-form-item>
        <el-form-item label="Summary">
          <el-input v-model="newIssue.summary" placeholder="Issue title" />
        </el-form-item>
        <el-form-item label="Description">
          <el-input v-model="newIssue.description" type="textarea" :rows="3" placeholder="Issue description (helps LLM match activities)" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="addIssue">Add</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const issues = ref([])
const dialogVisible = ref(false)
const newIssue = ref({ issue_key: '', summary: '', description: '' })

async function loadIssues() { const res = await api.getIssues(); issues.value = res.data }

async function addIssue() {
  if (!newIssue.value.issue_key) { ElMessage.warning('Issue key is required'); return }
  try {
    await api.addIssue(newIssue.value)
    ElMessage.success('Issue added'); dialogVisible.value = false
    newIssue.value = { issue_key: '', summary: '', description: '' }
    await loadIssues()
  } catch (e) { ElMessage.error(e.response?.data?.detail || 'Failed to add issue') }
}

async function toggleActive(row) { await api.updateIssue(row.issue_key, { is_active: row.is_active }) }

async function deleteIssue(key) {
  await ElMessageBox.confirm(`Delete issue ${key}?`, 'Confirm')
  await api.deleteIssue(key); ElMessage.success('Deleted'); await loadIssues()
}

onMounted(loadIssues)
</script>
