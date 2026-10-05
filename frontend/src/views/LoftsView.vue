<script setup>
import { onMounted, ref } from 'vue'
import api from '../api'

const lofts = ref([])
const error = ref('')
const loading = ref(false)
const savingId = ref(null)
// 每行独立的改名草稿与行内报错：{ [loftId]: { name, error } }
const drafts = ref({})

async function load() {
  error.value = ''
  loading.value = true
  try {
    const { data } = await api.get('/lofts/')
    lofts.value = data.results || data
    // 用服务端最新名重置草稿，保证回到专页看到的就是当前间名
    drafts.value = {}
    lofts.value.forEach((loft) => {
      drafts.value[loft.id] = { name: loft.name, error: '' }
    })
  } catch (e) {
    if (e.response?.status === 403) {
      error.value = e.response?.data?.detail || '操作工无权改名，仅管理员可使用改名台。'
    } else {
      error.value = '帆布间列表加载失败'
    }
  } finally {
    loading.value = false
  }
}

async function renameLoft(loft) {
  const state = drafts.value[loft.id]
  state.error = ''
  const newName = state.name.trim()
  if (!newName) {
    state.error = '新名不得为空'
    return
  }
  if (newName === loft.name) return

  savingId.value = loft.id
  try {
    const { data } = await api.post(`/lofts/${loft.id}/rename/`, { name: newName })
    const idx = lofts.value.findIndex((l) => l.id === loft.id)
    if (idx !== -1) lofts.value[idx] = data
    drafts.value[loft.id] = { name: data.name, error: '' }
  } catch (e) {
    const data = e.response?.data
    if (e.response?.status === 403) {
      state.error = data?.detail || '操作工禁止改名'
    } else {
      state.error =
        data?.name?.[0] ||
        data?.detail ||
        '改名失败（新名不得为空，且两间不得撞名）'
    }
  } finally {
    savingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1>帆布间改名台</h1>
    <p class="sub">仅管理员可改间名。改名后，晾晒架间名、布卷挂签所属间、浸渍流水间名全部跟随新名；不会删卷，也不会改动卷态。</p>
    <p v-if="error" class="error">{{ error }}</p>

    <table>
      <thead>
        <tr>
          <th>帆布间</th>
          <th>库位</th>
          <th>布卷数</th>
          <th style="width: 320px">新间名</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="loft in lofts" :key="loft.id">
          <td>{{ loft.name }}</td>
          <td>{{ loft.location || '—' }}</td>
          <td>{{ loft.rollCount }}</td>
          <td>
            <input
              v-model="drafts[loft.id].name"
              type="text"
              maxlength="120"
              :disabled="savingId === loft.id"
              @keyup.enter="renameLoft(loft)"
            />
            <p v-if="drafts[loft.id].error" class="error" style="margin:6px 0 0;font-size:0.85rem">
              {{ drafts[loft.id].error }}
            </p>
          </td>
          <td>
            <button
              class="btn"
              type="button"
              :disabled="savingId === loft.id"
              @click="renameLoft(loft)"
            >
              {{ savingId === loft.id ? '提交中…' : '改名' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="!loading && !lofts.length && !error" class="hint">尚无帆布间</p>
  </div>
</template>
