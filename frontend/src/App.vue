<template>
  <div id="app">
    <header class="navbar">
      <div class="navbar-brand">股票分析助手</div>
      <nav>
        <RouterLink to="/" class="nav-link">工作台</RouterLink>
        <RouterLink to="/analysis" class="nav-link">组合分析</RouterLink>
        <RouterLink to="/history" class="nav-link">历史记录</RouterLink>
        <RouterLink to="/settings" class="nav-link">系统设置</RouterLink>
      </nav>
    </header>
    <main>
      <RouterView />
    </main>
    <div v-if="toast.show" :class="['toast', `toast-${toast.type}`]">
      {{ toast.message }}
    </div>
  </div>
</template>

<script setup>
import { ref, provide } from 'vue'

const toast = ref({ show: false, message: '', type: 'success' })
let toastTimer = null

function showToast(message, type = 'success') {
  toast.value = { show: true, message, type }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toast.value.show = false
  }, 3000)
}

provide('toast', showToast)
</script>
