<template>
  <div class="issues-page">
    <div class="page-header">
      <h2>Jira Issues</h2>
      <el-button type="primary" round @click="dialogVisible = true">
        Add Issue
      </el-button>
    </div>

    <div class="issues-card">
      <el-table :data="issues">
        <el-table-column prop="issue_key" label="Key" width="150">
          <template #default="{ row }">
            <span class="issue-key">{{ row.issue_key }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="Summary">
          <template #default="{ row }">
            <span class="issue-summary">{{ row.summary }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Active" width="100">
          <template #default="{ row }">
            <el-switch v-model="row.is_active" @change="toggleActive(row)" />
          </template>
        </el-table-column>
        <el-table-column label="" width="80" align="center">
          <template #default="{ row }">
            <el-button type="danger" size="small" text @click="deleteIssue(row.issue_key)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="issues.length === 0" class="empty-state">
        No issues configured yet
      </div>
    </div>

    <!-- Add Issue Dialog -->
    <el-dialog v-model="dialogVisible" title="Add Jira Issue" width="500px">
      <el-form :model="newIssue" label-position="top" class="add-form">
        <el-form-item label="Issue Key" required>
          <el-input v-model="newIssue.issue_key" placeholder="e.g. PROJ-101" />
        </el-form-item>
        <el-form-item label="Summary">
          <el-input v-model="newIssue.summary" placeholder="Issue title" />
        </el-form-item>
        <el-form-item label="Description">
          <el-input
            v-model="newIssue.description"
            type="textarea"
            :rows="3"
            placeholder="Issue description (helps LLM match activities)"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button round @click="dialogVisible = false">Cancel</el-button>
        <el-button type="primary" round @click="addIssue">Add Issue</el-button>
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

<style scoped>
.issues-page {
  max-width: 800px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.issues-card {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
  padding: 4px 0;
}

.issue-key {
  font-weight: 600;
  color: var(--accent);
  font-size: 14px;
}

.issue-summary {
  font-size: 14px;
  color: var(--text-primary);
}

.add-form {
  padding: 0 4px;
}

.empty-state {
  text-align: center;
  padding: 48px;
  color: var(--text-tertiary);
  font-size: 14px;
}
</style>
