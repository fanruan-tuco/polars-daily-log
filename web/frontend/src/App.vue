<template>
  <div class="app-layout">
    <!-- Top Navigation -->
    <nav class="top-nav">
      <div class="nav-inner">
        <router-link to="/" class="nav-logo">
          <img src="/logo.png" alt="Polars" class="logo-img" />
          <span class="logo-text">Polars Daily Log</span>
        </router-link>

        <div class="nav-links">
          <router-link
            v-for="link in navLinks"
            :key="link.path"
            :to="link.path"
            class="nav-link"
            :class="{ active: isActive(link.path) }"
          >
            {{ link.label }}
          </router-link>
        </div>

        <div class="nav-spacer"></div>
      </div>
    </nav>

    <!-- Main Content -->
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()

const navLinks = [
  { path: '/', label: 'Dashboard' },
  { path: '/activities', label: 'Activities' },
  { path: '/my-logs', label: 'My Logs' },
  { path: '/issues', label: 'Issues' },
  { path: '/settings', label: 'Settings' },
]

function isActive(path) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  background: var(--bg);
}

.top-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--border);
  height: 52px;
}

.nav-inner {
  max-width: 1200px;
  margin: 0 auto;
  height: 100%;
  display: flex;
  align-items: center;
  padding: 0 24px;
}

.nav-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: var(--text-primary);
  flex-shrink: 0;
}

.logo-img {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.logo-text {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.3px;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0 auto;
}

.nav-link {
  text-decoration: none;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  padding: 6px 16px;
  border-radius: 980px;
  transition: all 0.2s ease;
  position: relative;
}

.nav-link:hover {
  color: var(--text-primary);
  background: rgba(0, 0, 0, 0.04);
}

.nav-link.active {
  color: var(--text-primary);
  background: rgba(0, 0, 0, 0.06);
}

.nav-spacer {
  width: 140px;
  flex-shrink: 0;
}

.main-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 84px 24px 48px;
}
</style>
