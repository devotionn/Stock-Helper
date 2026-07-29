<template>
  <div class="page-container">
    <h1 class="page-title">工作台</h1>

    <div v-if="loading" class="loading">
      <div class="loading-spinner"></div>
      <div>正在加载模块...</div>
    </div>

    <div v-else-if="error" class="empty-state">
      加载失败：{{ error }}
      <div class="mt-4">
        <button class="btn btn-primary" @click="loadCards">重新加载</button>
      </div>
    </div>

    <div v-else class="module-grid">
      <div
        v-for="card in cards"
        :key="card.module_id"
        :class="['module-card', { 'has-content': card.has_content }]"
        @click="goToModule(card.module_id)"
      >
        <div class="module-card-number">{{ card.module_id + 1 }}</div>
        <div class="module-card-name">{{ card.module_name }}</div>
        <div class="module-card-desc">{{ card.module_desc }}</div>
        <div class="module-card-info">
          <span v-if="card.text_summary">{{ card.text_summary }}</span>
          <span v-else class="text-secondary">暂无文字内容</span>
          <span>图片：{{ card.image_count }} 张</span>
          <span v-if="card.updated_at">最后更新：{{ card.updated_at }}</span>
        </div>
        <span
          :class="['module-card-status', card.has_content ? 'status-entered' : 'status-empty']"
        >
          {{ card.has_content ? '已录入' : '未录入' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { modulesApi } from '../api'

const router = useRouter()
const showToast = inject('toast')

const cards = ref([])
const loading = ref(true)
const error = ref('')

async function loadCards() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await modulesApi.getCards()
    cards.value = data
  } catch (e) {
    error.value = e.message || '未知错误'
    showToast('加载模块失败', 'error')
  } finally {
    loading.value = false
  }
}

function goToModule(id) {
  router.push(`/module/${id}`)
}

onMounted(loadCards)
</script>
