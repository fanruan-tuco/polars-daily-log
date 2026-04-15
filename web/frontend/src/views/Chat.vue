<template>
  <div class="chat-view">
    <!-- Page header -->
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">Chat</h2>
        <div class="page-subtitle">基于你最近 7 天的工作日志和活动摘要答题</div>
      </div>
      <div class="page-header-right">
        <el-button
          v-if="history.length > 0"
          round
          size="small"
          :disabled="busy"
          @click="resetChat"
        >新建对话</el-button>
      </div>
    </div>

    <!-- Chat container -->
    <div class="chat-shell">
      <!-- Message log -->
      <div ref="logEl" class="log">
        <!-- Intro / suggestions -->
        <div v-if="history.length === 0" class="intro">
          <div class="intro-hero">
            <div class="intro-eyebrow">对话助手</div>
            <h3 class="intro-title">问问你自己都做了什么。</h3>
            <p class="intro-sub">
              我读你本地数据库里的 <code>worklog_drafts.full_summary</code> 和
              <code>activities.llm_summary</code>（最近 7 天），基于真实记录答题。
            </p>
          </div>
          <div class="suggestions">
            <button
              v-for="s in suggestions" :key="s"
              class="suggestion"
              type="button"
              :disabled="busy"
              @click="ask(s)"
            >{{ s }}</button>
          </div>
        </div>

        <!-- Messages -->
        <div
          v-for="(m, idx) in history"
          :key="idx"
          class="msg"
          :class="m.role"
        >
          <div class="bubble" :class="{ error: m.error }">
            <div v-if="m.role === 'ai'" class="rendered" v-html="renderMd(m.text)"></div>
            <template v-else>{{ m.text }}</template>
          </div>
          <a
            v-if="m.error && idx === history.length - 1 && !busy"
            class="retry-link"
            href="#"
            @click.prevent="retry(idx)"
          >重试</a>
        </div>

        <!-- Typing indicator -->
        <div v-if="busy && !streaming" class="msg ai">
          <div class="typing">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>

      <!-- Input bar -->
      <div class="inputbar">
        <textarea
          ref="boxEl"
          v-model="draft"
          class="box"
          rows="1"
          :placeholder="boxPlaceholder"
          :disabled="busy"
          @keydown="onKey"
          @input="autosize"
        />
        <el-button
          v-if="!busy"
          type="primary"
          round
          :disabled="!draft.trim()"
          @click="sendFromBox"
        >发送</el-button>
        <el-button
          v-else
          type="default"
          round
          @click="stop"
        >停止</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'

const SESSION_STORAGE_KEY = 'pdl_chat_session_id'

const history = ref([])    // [{role:'user'|'ai', text, error?}]
const draft = ref('')
const busy = ref(false)
const streaming = ref(false)
const logEl = ref(null)
const boxEl = ref(null)

const sessionId = ref(null)
// Live AbortController for the in-flight fetch — mutated on ask()/stop().
let controller = null

const suggestions = [
  '最近一周干了啥？',
  '今天的主要工作有哪些？',
  '最近在哪个 Jira 任务上花时间最多？',
  '总结一下这周的开发主线。',
]

const boxPlaceholder = computed(() =>
  busy.value ? '生成中...' : '问点什么... (Enter 发送, Shift+Enter 换行)'
)

function scrollToBottom() {
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

function autosize() {
  nextTick(() => {
    if (!boxEl.value) return
    boxEl.value.style.height = 'auto'
    boxEl.value.style.height = Math.min(boxEl.value.scrollHeight, 140) + 'px'
  })
}

function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendFromBox()
  }
}

function sendFromBox() {
  const text = draft.value.trim()
  if (!text) return
  draft.value = ''
  autosize()
  ask(text)
}

function resetChat() {
  if (busy.value) return
  localStorage.removeItem(SESSION_STORAGE_KEY)
  sessionId.value = null
  history.value = []
  draft.value = ''
  autosize()
}

function stop() {
  if (controller) {
    try { controller.abort() } catch (_) { /* noop */ }
  }
}

function retry(errorIdx) {
  // Walk back from the error bubble to find the last user message. Drop
  // the error bubble before resending so it doesn't leak into the next
  // prompt's history.
  let lastUserText = ''
  for (let i = errorIdx - 1; i >= 0; i--) {
    if (history.value[i].role === 'user') {
      lastUserText = history.value[i].text
      break
    }
  }
  if (!lastUserText) return
  // Drop the error bubble AND the most recent user message (ask() will
  // re-push it so history/messages stay consistent with the request).
  history.value.splice(errorIdx, 1)
  for (let i = history.value.length - 1; i >= 0; i--) {
    if (history.value[i].role === 'user' && history.value[i].text === lastUserText) {
      history.value.splice(i, 1)
      break
    }
  }
  ask(lastUserText)
}

// Lightweight markdown renderer — matches DEFAULT_CHAT_PROMPT's output surface.
// Handles ### headers, **bold**, `code`, "- " bullets, line breaks.
function renderMd(md) {
  if (!md) return ''
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const inline = (s) =>
    esc(s)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')

  const lines = md.split(/\r?\n/)
  let out = ''
  let inList = false
  for (const raw of lines) {
    const line = raw.trimEnd()
    if (/^###\s+/.test(line)) {
      if (inList) { out += '</ul>'; inList = false }
      out += '<h4>' + inline(line.replace(/^###\s+/, '')) + '</h4>'
    } else if (/^-\s+/.test(line)) {
      if (!inList) { out += '<ul>'; inList = true }
      out += '<li>' + inline(line.replace(/^-\s+/, '')) + '</li>'
    } else if (line === '') {
      if (inList) { out += '</ul>'; inList = false }
    } else {
      if (inList) { out += '</ul>'; inList = false }
      out += inline(line) + '<br/>'
    }
  }
  if (inList) out += '</ul>'
  return out
}

async function ask(text) {
  if (busy.value || !text.trim()) return
  busy.value = true
  streaming.value = false
  controller = new AbortController()

  history.value.push({ role: 'user', text })
  scrollToBottom()

  // Index into history.value for the AI bubble being streamed. We write
  // through the reactive proxy (history.value[aiIdx].text = ...) rather
  // than holding a raw-object reference — the latter bypasses Vue's
  // reactivity and leaves the bubble stuck on whatever rendered first.
  let aiIdx = -1
  let assembled = ''

  try {
    const body = {
      messages: history.value.map(m => ({ role: m.role, text: m.text })),
    }
    if (sessionId.value) body.session_id = sessionId.value

    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    if (!resp.ok) throw new Error('HTTP ' + resp.status)

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const chunk = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const dataLine = chunk.split('\n').find(l => l.startsWith('data: '))
        if (!dataLine) continue
        const payload = dataLine.slice(6).trim()
        if (payload === '[DONE]') continue
        try {
          const evt = JSON.parse(payload)
          if (evt.session_id !== undefined) {
            // Control event — pin the fresh session id to localStorage
            // so a reload picks up right where we left off.
            sessionId.value = evt.session_id
            try { localStorage.setItem(SESSION_STORAGE_KEY, evt.session_id) } catch (_) {}
          } else if (evt.text !== undefined) {
            if (aiIdx < 0) {
              aiIdx = history.value.length
              history.value.push({ role: 'ai', text: '' })
              streaming.value = true
            }
            assembled += evt.text
            history.value[aiIdx].text = assembled
            scrollToBottom()
          } else if (evt.error) {
            history.value.push({ role: 'ai', text: '错误: ' + evt.error, error: true })
            scrollToBottom()
            break
          }
        } catch (_) {
          // ignore malformed event
        }
      }
    }
  } catch (err) {
    if (err && err.name === 'AbortError') {
      // User clicked 停止 — swallow silently. Any partial AI bubble
      // already streamed stays put as an honest record of what arrived.
    } else {
      history.value.push({ role: 'ai', text: '请求失败: ' + err.message, error: true })
      ElMessage.error('Chat 请求失败')
      scrollToBottom()
    }
  } finally {
    busy.value = false
    streaming.value = false
    controller = null
    boxEl.value && boxEl.value.focus()
  }
}

async function restoreSession() {
  let saved = null
  try { saved = localStorage.getItem(SESSION_STORAGE_KEY) } catch (_) { return }
  if (!saved) return
  try {
    const resp = await fetch(`/api/chat/sessions/${encodeURIComponent(saved)}/messages`)
    if (resp.status === 404) {
      localStorage.removeItem(SESSION_STORAGE_KEY)
      return
    }
    if (!resp.ok) return  // transient error — leave id alone, user can retry by sending
    const rows = await resp.json()
    sessionId.value = saved
    // Map {role, text} only; drop created_at so the history shape stays
    // identical to freshly-sent messages.
    history.value = rows.map(r => ({ role: r.role, text: r.text }))
    scrollToBottom()
  } catch (_) {
    // Network error on boot — don't wipe the id, just skip restoration.
  }
}

onMounted(async () => {
  autosize()
  await restoreSession()
  boxEl.value && boxEl.value.focus()
})
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  /* Fill available main area height (main has padding 32px top/48px bottom) */
  height: calc(100vh - 80px);
  min-height: 520px;
}

/* Reuse page-header pattern from other views */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 20px;
  flex-shrink: 0;
}
.page-title {
  margin: 0 0 4px;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--ink);
}
.page-subtitle {
  font-size: 13px;
  color: var(--ink-muted);
}

/* Chat shell: message log + input bar */
.chat-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow);
}

.log {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  scroll-behavior: smooth;
}

/* Intro / suggestions */
.intro {
  margin: auto;
  max-width: 560px;
  text-align: center;
  padding: 32px 16px;
}
.intro-eyebrow {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-dim);
  margin-bottom: 12px;
}
.intro-title {
  margin: 0 0 12px;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--ink);
}
.intro-sub {
  margin: 0 0 28px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--ink-muted);
}
.intro-sub code {
  background: rgba(0, 0, 0, 0.05);
  padding: 1px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-soft);
}
.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}
.suggestion {
  padding: 8px 14px;
  font-size: 13px;
  font-family: inherit;
  color: var(--ink-soft);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  cursor: pointer;
  transition: var(--transition);
}
.suggestion:hover:not(:disabled) {
  border-color: var(--ink);
  color: var(--ink);
  background: var(--surface-hover);
}
.suggestion:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Messages */
.msg {
  display: flex;
  flex-direction: column;
  max-width: 100%;
  animation: slideIn 0.22s ease-out;
}
@keyframes slideIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
.msg.user { align-self: flex-end; max-width: 82%; align-items: flex-end; }
.msg.ai   { align-self: flex-start; max-width: 92%; align-items: flex-start; }

.bubble {
  padding: 11px 16px;
  border-radius: var(--radius);
  line-height: 1.65;
  font-size: 14px;
  word-wrap: break-word;
  white-space: pre-wrap;
}
.msg.user .bubble {
  background: var(--ink);
  color: #ffffff;
  border-bottom-right-radius: 4px;
}
.msg.ai .bubble {
  background: var(--surface-hover);
  color: var(--ink-soft);
  border: 1px solid var(--line);
  border-bottom-left-radius: 4px;
}
.bubble.error {
  border-color: var(--danger) !important;
  background: rgba(209, 69, 59, 0.06) !important;
  color: var(--danger) !important;
}

.retry-link {
  margin-top: 6px;
  font-size: 12px;
  color: var(--ink-muted);
  text-decoration: none;
  cursor: pointer;
}
.retry-link:hover {
  color: var(--ink);
  text-decoration: underline;
}

.bubble .rendered { white-space: normal; }
.bubble :deep(h4) {
  font-size: 14px;
  font-weight: 700;
  margin: 12px 0 6px;
  color: var(--ink);
  letter-spacing: -0.01em;
}
.bubble :deep(h4:first-child) { margin-top: 0; }
.bubble :deep(strong) { color: var(--ink); font-weight: 600; }
.bubble :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 1px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--ink);
}
.bubble :deep(ul) {
  margin: 6px 0;
  padding-left: 20px;
}
.bubble :deep(li) { margin: 3px 0; }

/* Typing indicator */
.typing {
  display: inline-flex;
  gap: 4px;
  padding: 14px 16px;
  background: var(--surface-hover);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  border-bottom-left-radius: 4px;
}
.typing span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ink-dim);
  animation: blink 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 60%, 100% { opacity: 0.3; }
  30% { opacity: 1; }
}

/* Input bar */
.inputbar {
  flex-shrink: 0;
  border-top: 1px solid var(--line);
  padding: 14px 16px;
  background: var(--surface);
  display: flex;
  gap: 10px;
  align-items: flex-end;
}
.box {
  flex: 1;
  resize: none;
  min-height: 42px;
  max-height: 140px;
  background: var(--surface-hover);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  color: var(--ink);
  padding: 10px 14px;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.55;
  outline: none;
  transition: border-color 0.15s;
}
.box:focus { border-color: var(--ink); }
.box:disabled { opacity: 0.6; cursor: not-allowed; }

@media (max-width: 900px) {
  .chat-view { height: calc(100vh - 96px); }
  .log { padding: 16px 18px; }
  .inputbar { padding: 12px; }
}
</style>
