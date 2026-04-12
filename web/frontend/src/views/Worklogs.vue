<template>
  <div class="worklogs-page">
    <div class="page-header">
      <h2>Work Logs</h2>
      <div class="header-actions">
        <el-date-picker
          v-model="selectedDate"
          type="date"
          value-format="YYYY-MM-DD"
          @change="loadDrafts"
        />
        <el-button type="warning" round @click="approveAll" :disabled="!hasPending">
          Approve All
        </el-button>
      </div>
    </div>

    <div v-if="drafts.length === 0" class="empty-state-card">
      <el-icon :size="48" color="var(--text-tertiary)"><Document /></el-icon>
      <p>No worklogs for this date</p>
    </div>

    <div class="drafts-list">
      <div v-for="draft in drafts" :key="draft.id" class="draft-card">
        <!-- Card Header -->
        <div class="draft-header">
          <div class="draft-header-left">
            <el-tag :type="statusType(draft.status)" size="small">{{ draft.status }}</el-tag>
            <span class="draft-issue">{{ draft.issue_key }}</span>
            <span v-if="draft.user_edited" class="draft-edited">edited</span>
          </div>
          <div class="draft-hours">
            {{ (draft.time_spent_sec / 3600).toFixed(1) }}h
          </div>
        </div>

        <!-- Card Body -->
        <div class="draft-body">
          <div v-if="editingId === draft.id" class="edit-form">
            <el-form label-position="top">
              <el-form-item label="Hours">
                <el-input-number v-model="editForm.hours" :min="0" :step="0.5" :precision="1" />
              </el-form-item>
              <el-form-item label="Summary">
                <el-input v-model="editForm.summary" type="textarea" :rows="4" />
              </el-form-item>
              <div class="edit-actions">
                <el-button type="primary" round @click="saveEdit(draft.id)">Save Changes</el-button>
                <el-button round @click="editingId = null">Cancel</el-button>
              </div>
            </el-form>
          </div>
          <div v-else class="draft-summary">
            {{ draft.summary }}
          </div>
        </div>

        <!-- Card Footer -->
        <div class="draft-footer" v-if="draft.status === 'pending_review'">
          <el-button size="small" round @click="startEdit(draft)">Edit</el-button>
          <el-button size="small" type="primary" round @click="approve(draft.id)">Approve</el-button>
          <el-button size="small" type="danger" round @click="reject(draft.id)">Reject</el-button>
        </div>
        <div class="draft-footer" v-else-if="draft.status === 'approved' || draft.status === 'auto_approved'">
          <el-button size="small" type="primary" round @click="submit(draft.id)">Submit to Jira</el-button>
        </div>
        <div class="draft-footer" v-else-if="draft.status === 'submitted'">
          <el-button size="small" round @click="showAudit(draft.id)">View Audit Trail</el-button>
        </div>
      </div>
    </div>

    <!-- Audit Trail Dialog -->
    <el-dialog v-model="auditVisible" title="Audit Trail" width="600px">
      <el-timeline>
        <el-timeline-item v-for="log in auditLogs" :key="log.id" :timestamp="log.created_at">
          <strong>{{ log.action }}</strong>
          <pre v-if="log.after_snapshot" class="audit-snapshot">{{ log.after_snapshot }}</pre>
        </el-timeline-item>
      </el-timeline>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const selectedDate = ref(new Date().toISOString().split('T')[0])
const drafts = ref([])
const editingId = ref(null)
const editForm = ref({ hours: 0, summary: '' })
const auditVisible = ref(false)
const auditLogs = ref([])

const hasPending = computed(() => drafts.value.some(d => d.status === 'pending_review'))

function statusType(status) {
  const map = { pending_review: 'warning', approved: 'success', auto_approved: 'success', submitted: 'info', rejected: 'danger', auto_rejected: 'danger' }
  return map[status] || ''
}

async function loadDrafts() {
  const res = await api.getWorklogs(selectedDate.value)
  drafts.value = res.data
}

function startEdit(draft) {
  editingId.value = draft.id
  editForm.value = { hours: draft.time_spent_sec / 3600, summary: draft.summary }
}

async function saveEdit(id) {
  await api.updateDraft(id, { time_spent_sec: Math.round(editForm.value.hours * 3600), summary: editForm.value.summary })
  editingId.value = null
  ElMessage.success('Draft updated')
  await loadDrafts()
}

async function approve(id) { await api.approveDraft(id); ElMessage.success('Approved'); await loadDrafts() }
async function reject(id) { await api.rejectDraft(id); ElMessage.warning('Rejected'); await loadDrafts() }
async function approveAll() { await api.approveAll(selectedDate.value); ElMessage.success('All approved'); await loadDrafts() }

async function submit(id) {
  try { await api.submitDraft(id); ElMessage.success('Submitted to Jira'); await loadDrafts() }
  catch (e) { ElMessage.error('Submit failed: ' + (e.response?.data?.detail || e.message)) }
}

async function showAudit(id) {
  const res = await api.getAuditTrail(id)
  auditLogs.value = res.data
  auditVisible.value = true
}

onMounted(loadDrafts)
</script>

<style scoped>
.worklogs-page {
  max-width: 800px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.empty-state-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 40px;
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

.empty-state-card p {
  color: var(--text-tertiary);
  font-size: 15px;
  margin-top: 12px;
}

.drafts-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.draft-card {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
  transition: all 0.2s ease;
}

.draft-card:hover {
  box-shadow: var(--shadow-lg);
}

.draft-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.draft-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.draft-issue {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
}

.draft-edited {
  font-size: 12px;
  color: var(--text-tertiary);
  font-style: italic;
}

.draft-hours {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
  font-variant-numeric: tabular-nums;
}

.draft-body {
  padding: 20px;
}

.draft-summary {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-line;
}

.edit-form {
  max-width: 500px;
}

.edit-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.draft-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  display: flex;
  gap: 8px;
}

.audit-snapshot {
  font-size: 12px;
  max-height: 200px;
  overflow: auto;
  background: var(--bg);
  padding: 12px;
  border-radius: var(--radius-sm);
  margin-top: 8px;
  font-family: "SF Mono", Menlo, Monaco, monospace;
}
</style>
