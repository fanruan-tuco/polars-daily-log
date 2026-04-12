<template>
  <div class="settings-page">
    <div class="page-header">
      <h2>Settings</h2>
    </div>

    <!-- Tab Navigation -->
    <div class="tab-nav">
      <button
        v-for="tab in tabs"
        :key="tab.name"
        :class="['tab-btn', { active: activeTab === tab.name }]"
        @click="activeTab = tab.name"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Monitor Tab -->
    <div v-show="activeTab === 'monitor'" class="tab-content">
      <div class="settings-card">
        <h4 class="card-title">Monitor Configuration</h4>
        <el-form label-position="top" class="settings-form">
          <el-form-item label="Sampling Interval (seconds)">
            <el-input-number v-model="settings.monitor_interval_sec" :min="10" :max="300" />
          </el-form-item>
          <el-form-item label="OCR Enabled">
            <el-switch v-model="settings.monitor_ocr_enabled" />
          </el-form-item>
          <el-form-item label="OCR Engine">
            <el-select v-model="settings.monitor_ocr_engine" style="width: 100%">
              <el-option label="Auto" value="auto" />
              <el-option label="Vision (macOS)" value="vision" />
              <el-option label="WinOCR (Windows)" value="winocr" />
              <el-option label="Tesseract" value="tesseract" />
            </el-select>
          </el-form-item>
          <el-form-item label="Screenshot Retention (days)">
            <el-input-number v-model="settings.monitor_screenshot_retention_days" :min="1" :max="90" />
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- Git Repos Tab -->
    <div v-show="activeTab === 'git'" class="tab-content">
      <div class="settings-card">
        <h4 class="card-title">Git Repositories</h4>
        <p class="card-description">Configure git repositories to track commits from.</p>

        <el-table :data="gitRepos" style="margin-bottom: 20px">
          <el-table-column prop="path" label="Path" />
          <el-table-column prop="author_email" label="Author Email" />
          <el-table-column label="" width="80" align="center">
            <template #default="{ row }">
              <el-button text type="danger" @click="removeRepo(row.id)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="add-repo-form">
          <el-input v-model="newRepo.path" placeholder="/path/to/repo" class="repo-input" />
          <el-input v-model="newRepo.author_email" placeholder="email@example.com" class="repo-input" />
          <el-button type="primary" round @click="addRepo">Add</el-button>
        </div>
      </div>
    </div>

    <!-- Jira Tab -->
    <div v-show="activeTab === 'jira'" class="tab-content">
      <div class="settings-card">
        <h4 class="card-title">Jira Connection</h4>
        <el-form label-position="top" class="settings-form">
          <el-form-item label="Server URL">
            <el-input v-model="settings.jira_server_url" placeholder="https://jira.example.com" />
          </el-form-item>
          <el-form-item label="Personal Access Token">
            <el-input v-model="settings.jira_pat" type="password" show-password />
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- LLM Tab -->
    <div v-show="activeTab === 'llm'" class="tab-content">
      <div class="settings-card">
        <h4 class="card-title">LLM Configuration</h4>
        <el-form label-position="top" class="settings-form">
          <el-form-item label="Engine">
            <el-select v-model="settings.llm_engine" style="width: 100%">
              <el-option label="Kimi (Moonshot)" value="kimi" />
              <el-option label="OpenAI" value="openai" />
              <el-option label="Ollama" value="ollama" />
              <el-option label="Claude" value="claude" />
            </el-select>
          </el-form-item>
          <el-form-item label="API Key">
            <el-input v-model="settings.llm_api_key" type="password" show-password />
          </el-form-item>
          <el-form-item label="Model">
            <el-input v-model="settings.llm_model" />
          </el-form-item>
          <el-form-item label="Base URL">
            <el-input v-model="settings.llm_base_url" />
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- Prompts Tab -->
    <div v-show="activeTab === 'prompts'" class="tab-content">
      <div class="settings-card">
        <el-alert type="info" :closable="false" style="margin-bottom: 24px">
          Prompt templates control how the LLM generates work logs. Changes take effect after saving.
        </el-alert>

        <div class="prompt-section">
          <h4 class="card-title">Log Generation Prompt</h4>
          <p class="card-description">
            <strong>Purpose:</strong> When the daily trigger fires, the system fills this template with the day's activity records,
            Git commits, and Jira task list, then sends it to the LLM to generate work log drafts.
          </p>
          <p class="card-hint">
            Available variables: <code>{date}</code>, <code>{jira_issues}</code>, <code>{git_commits}</code>, <code>{activities}</code>
          </p>
          <el-input v-model="settings.summarize_prompt" type="textarea" :rows="12" />
        </div>

        <div class="prompt-section">
          <h4 class="card-title">Auto-Approve Prompt</h4>
          <p class="card-description">
            <strong>Purpose:</strong> At the configured auto-approve time (default 18:30), if there are still unreviewed daily drafts,
            the system sends each draft to the LLM for quality assessment. Passing drafts are auto-approved and submitted to Jira.
          </p>
          <p class="card-hint">
            Available variables: <code>{date}</code>, <code>{issue_key}</code>, <code>{issue_summary}</code>,
            <code>{time_spent_hours}</code>, <code>{summary}</code>, <code>{git_commits}</code>
          </p>
          <el-input v-model="settings.auto_approve_prompt" type="textarea" :rows="12" />
        </div>
      </div>
    </div>

    <!-- Scheduler Tab -->
    <div v-show="activeTab === 'scheduler'" class="tab-content">
      <div class="settings-card">
        <h4 class="card-title">Scheduler</h4>
        <el-form label-position="top" class="settings-form">
          <el-form-item label="Daily Trigger Enabled">
            <el-switch v-model="settings.scheduler_enabled" />
          </el-form-item>
          <el-form-item label="Trigger Time">
            <el-time-picker v-model="settings.scheduler_trigger_time" format="HH:mm" value-format="HH:mm" />
          </el-form-item>
          <el-form-item label="Auto-Approve Enabled">
            <el-switch v-model="settings.auto_approve_enabled" />
          </el-form-item>
          <el-form-item label="Auto-Approve & Submit Time">
            <el-time-picker v-model="settings.auto_approve_trigger_time" format="HH:mm" value-format="HH:mm" />
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- Save Button -->
    <div class="save-bar">
      <el-button type="primary" round size="large" @click="saveAll">
        Save All Settings
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const activeTab = ref('monitor')
const tabs = [
  { name: 'monitor', label: 'Monitor' },
  { name: 'git', label: 'Git Repos' },
  { name: 'jira', label: 'Jira' },
  { name: 'llm', label: 'LLM' },
  { name: 'prompts', label: 'Prompts' },
  { name: 'scheduler', label: 'Scheduler' },
]

const settings = ref({
  monitor_interval_sec: 30, monitor_ocr_enabled: true, monitor_ocr_engine: 'auto',
  monitor_screenshot_retention_days: 7, jira_server_url: '', jira_pat: '',
  llm_engine: 'kimi', llm_api_key: '', llm_model: '', llm_base_url: '',
  summarize_prompt: '', auto_approve_prompt: '',
  scheduler_enabled: true, scheduler_trigger_time: '18:00',
  auto_approve_enabled: true, auto_approve_trigger_time: '21:30',
})
const gitRepos = ref([])
const newRepo = ref({ path: '', author_email: '' })

async function loadSettings() {
  const res = await api.getSettings()
  for (const item of res.data) {
    if (item.key in settings.value) {
      const val = item.value
      if (val === 'true') settings.value[item.key] = true
      else if (val === 'false') settings.value[item.key] = false
      else if (!isNaN(Number(val)) && val !== '') settings.value[item.key] = Number(val)
      else settings.value[item.key] = val
    }
  }
}

async function loadGitRepos() {
  try { const res = await api.getGitRepos(); gitRepos.value = res.data } catch (e) { /* ignore */ }
}

async function addRepo() {
  if (!newRepo.value.path) return
  await api.addGitRepo(newRepo.value)
  newRepo.value = { path: '', author_email: '' }
  await loadGitRepos()
}

async function removeRepo(id) {
  await api.deleteGitRepo(id)
  await loadGitRepos()
}

async function saveAll() {
  for (const [key, value] of Object.entries(settings.value)) {
    await api.putSetting(key, String(value))
  }
  ElMessage.success('Settings saved')
}

onMounted(() => { loadSettings(); loadGitRepos() })
</script>

<style scoped>
.settings-page {
  max-width: 800px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.tab-nav {
  display: flex;
  gap: 6px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.tab-btn {
  padding: 8px 18px;
  border: none;
  background: transparent;
  border-radius: 980px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: var(--font);
}

.tab-btn:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--text-primary);
}

.tab-btn.active {
  background: var(--text-primary);
  color: #fff;
}

.tab-content {
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.settings-card {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 28px;
}

.card-title {
  font-size: 17px;
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--text-primary);
}

.card-description {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 20px;
  line-height: 1.5;
}

.card-hint {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-bottom: 12px;
}

.card-hint code {
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  font-family: "SF Mono", Menlo, Monaco, monospace;
}

.settings-form {
  max-width: 500px;
  margin-top: 20px;
}

.settings-form .el-form-item {
  margin-bottom: 24px;
}

.prompt-section {
  margin-bottom: 32px;
}

.prompt-section:last-child {
  margin-bottom: 0;
}

.add-repo-form {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.repo-input {
  flex: 1;
}

.save-bar {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--border);
}
</style>
