<template>
  <div>
    <h2 style="margin-bottom: 20px">Settings</h2>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="Monitor" name="monitor">
        <el-form label-width="200px" style="max-width: 600px">
          <el-form-item label="Sampling Interval (sec)">
            <el-input-number v-model="settings.monitor_interval_sec" :min="10" :max="300" />
          </el-form-item>
          <el-form-item label="OCR Enabled">
            <el-switch v-model="settings.monitor_ocr_enabled" />
          </el-form-item>
          <el-form-item label="OCR Engine">
            <el-select v-model="settings.monitor_ocr_engine">
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
      </el-tab-pane>

      <el-tab-pane label="Git Repos" name="git">
        <p style="color: #909399; margin-bottom: 16px">Configure git repositories to track commits from.</p>
        <el-table :data="gitRepos" stripe style="margin-bottom: 16px">
          <el-table-column prop="path" label="Path" />
          <el-table-column prop="author_email" label="Author Email" />
          <el-table-column label="Actions" width="80">
            <template #default="{ row }">
              <el-button text type="danger" @click="removeRepo(row.id)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-form inline>
          <el-form-item>
            <el-input v-model="newRepo.path" placeholder="/path/to/repo" />
          </el-form-item>
          <el-form-item>
            <el-input v-model="newRepo.author_email" placeholder="email@example.com" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="addRepo">Add</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="Jira" name="jira">
        <el-form label-width="160px" style="max-width: 600px">
          <el-form-item label="Server URL">
            <el-input v-model="settings.jira_server_url" placeholder="https://jira.example.com" />
          </el-form-item>
          <el-form-item label="Personal Access Token">
            <el-input v-model="settings.jira_pat" type="password" show-password />
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="LLM" name="llm">
        <el-form label-width="160px" style="max-width: 600px">
          <el-form-item label="Engine">
            <el-select v-model="settings.llm_engine">
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
      </el-tab-pane>

      <el-tab-pane label="Prompt 模板" name="prompts">
        <el-alert type="info" :closable="false" style="margin-bottom: 20px">
          Prompt 模板用于控制 LLM 生成工作日志的行为。修改后点击底部「保存」按钮生效。
        </el-alert>

        <h4>日志生成 Prompt</h4>
        <p style="color: #606266; font-size: 13px; margin-bottom: 4px">
          <strong>用途：</strong>每天定时触发时，系统将当天的活动记录、Git commits 和 Jira 任务列表填入此模板，
          发送给 LLM 生成工作日志草稿。每个 Jira 任务会生成一条包含工时和摘要的草稿。
        </p>
        <p style="color: #909399; font-size: 12px; margin-bottom: 8px">
          可用变量：<code>{date}</code> 日期、<code>{jira_issues}</code> 活跃任务列表、<code>{git_commits}</code> 当天提交记录、<code>{activities}</code> 活动采集记录
        </p>
        <el-input v-model="settings.summarize_prompt" type="textarea" :rows="12" />

        <h4 style="margin-top: 24px">自动审批 Prompt</h4>
        <p style="color: #606266; font-size: 13px; margin-bottom: 4px">
          <strong>用途：</strong>日志草稿生成后，若超过设定时间（默认 30 分钟）无人审批，系统会将每条草稿发送给 LLM，
          由 LLM 判断日志质量是否合格。合格则自动通过并提交到 Jira，不合格则保持待审批状态等待人工处理。
        </p>
        <p style="color: #909399; font-size: 12px; margin-bottom: 8px">
          可用变量：<code>{date}</code> 日期、<code>{issue_key}</code> 任务编号、<code>{issue_summary}</code> 任务标题、<code>{time_spent_hours}</code> 工时、<code>{summary}</code> 日志内容、<code>{git_commits}</code> 关联提交
        </p>
        <el-input v-model="settings.auto_approve_prompt" type="textarea" :rows="12" />
      </el-tab-pane>

      <el-tab-pane label="Scheduler" name="scheduler">
        <el-form label-width="200px" style="max-width: 600px">
          <el-form-item label="Daily Trigger Enabled">
            <el-switch v-model="settings.scheduler_enabled" />
          </el-form-item>
          <el-form-item label="Trigger Time">
            <el-time-picker v-model="settings.scheduler_trigger_time" format="HH:mm" value-format="HH:mm" />
          </el-form-item>
          <el-form-item label="Auto-Approve Enabled">
            <el-switch v-model="settings.auto_approve_enabled" />
          </el-form-item>
          <el-form-item label="Auto-Approve Timeout (min)">
            <el-input-number v-model="settings.auto_approve_timeout_min" :min="5" :max="120" />
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <div style="margin-top: 20px">
      <el-button type="primary" @click="saveAll">Save All Settings</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const activeTab = ref('monitor')
const settings = ref({
  monitor_interval_sec: 30, monitor_ocr_enabled: true, monitor_ocr_engine: 'auto',
  monitor_screenshot_retention_days: 7, jira_server_url: '', jira_pat: '',
  llm_engine: 'kimi', llm_api_key: '', llm_model: '', llm_base_url: '',
  summarize_prompt: '', auto_approve_prompt: '',
  scheduler_enabled: true, scheduler_trigger_time: '18:00',
  auto_approve_enabled: true, auto_approve_timeout_min: 30,
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
