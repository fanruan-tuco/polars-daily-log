<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px">
      <h2>Work Logs</h2>
      <div>
        <el-date-picker v-model="selectedDate" type="date" value-format="YYYY-MM-DD" @change="loadDrafts" style="margin-right: 10px" />
        <el-button type="warning" @click="approveAll" :disabled="!hasPending">Approve All</el-button>
      </div>
    </div>

    <div v-if="drafts.length === 0">
      <el-empty description="No worklogs for this date" />
    </div>

    <el-card v-for="draft in drafts" :key="draft.id" style="margin-bottom: 16px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <div>
            <el-tag :type="statusType(draft.status)" style="margin-right: 8px">{{ draft.status }}</el-tag>
            <strong>{{ draft.issue_key }}</strong>
            <span v-if="draft.user_edited" style="margin-left: 8px; color: #909399; font-size: 12px">(edited)</span>
          </div>
          <div>
            <span style="font-size: 18px; font-weight: bold; margin-right: 16px">
              {{ (draft.time_spent_sec / 3600).toFixed(1) }}h
            </span>
          </div>
        </div>
      </template>

      <div v-if="editingId === draft.id">
        <el-form label-width="80px">
          <el-form-item label="Hours">
            <el-input-number v-model="editForm.hours" :min="0" :step="0.5" :precision="1" />
          </el-form-item>
          <el-form-item label="Summary">
            <el-input v-model="editForm.summary" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveEdit(draft.id)">Save</el-button>
            <el-button @click="editingId = null">Cancel</el-button>
          </el-form-item>
        </el-form>
      </div>
      <div v-else>
        <p>{{ draft.summary }}</p>
      </div>

      <template #footer v-if="draft.status === 'pending_review'">
        <el-button type="primary" size="small" @click="startEdit(draft)">Edit</el-button>
        <el-button type="success" size="small" @click="approve(draft.id)">Approve</el-button>
        <el-button type="danger" size="small" @click="reject(draft.id)">Reject</el-button>
      </template>
      <template #footer v-else-if="draft.status === 'approved' || draft.status === 'auto_approved'">
        <el-button type="primary" size="small" @click="submit(draft.id)">Submit to Jira</el-button>
      </template>
      <template #footer v-else-if="draft.status === 'submitted'">
        <el-button size="small" @click="showAudit(draft.id)">View Audit Trail</el-button>
      </template>
    </el-card>

    <el-dialog v-model="auditVisible" title="Audit Trail" width="600px">
      <el-timeline>
        <el-timeline-item v-for="log in auditLogs" :key="log.id" :timestamp="log.created_at">
          <strong>{{ log.action }}</strong>
          <pre v-if="log.after_snapshot" style="font-size: 12px; max-height: 200px; overflow: auto">{{ log.after_snapshot }}</pre>
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
