<script setup>
import { onMounted, ref } from 'vue'
import api from '../api'

const lofts = ref([])
const error = ref('')
const busyId = ref(null)
const editingId = ref(null)
const draftName = ref('')
const rowError = ref('')
const okMsg = ref('')

async function load() {
  error.value = ''
  try {
    const { data } = await api.get('/lofts/')
    lofts.value = data.results || data
  } catch {
    error.value = '帆布间列表加载失败'
  }
}

function startEdit(row) {
  editingId.value = row.id
  draftName.value = row.name
  rowError.value = ''
  okMsg.value = ''
}

function cancelEdit() {
  editingId.value = null
  draftName.value = ''
  rowError.value = ''
}

async function submitName(row) {
  rowError.value = ''
  okMsg.value = ''
  const name = draftName.value.trim()
  if (!name) {
    rowError.value = '新名不得为空'
    return
  }
  if (name === row.name) {
    cancelEdit()
    return
  }
  busyId.value = row.id
  try {
    // 专用改名动作：后端只认 name，不会动布卷或卷态
    await api.post(`/lofts/${row.id}/rename/`, { name })
    editingId.value = null
    draftName.value = ''
    okMsg.value = `「${row.name}」已更名为「${name}」；架面、挂签、浸渍流水均显示新名。`
    await load()
  } catch (e) {
    const data = e.response?.data
    rowError.value =
      data?.name?.[0] ||
      data?.detail ||
      (e.response?.status === 403
        ? '仅管理员可改间名'
        : e.response?.status === 409
          ? '已存在同名帆布间，两间不得撞名'
          : '改名失败')
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="lofts-page">
    <h1>帆布间改名台</h1>
    <p class="sub">管理员专页：仅改帆布间名称。改名不会删除布卷、不会改动任何卷态；晾晒架、布卷挂签、浸渍流水随后统一显示新名。</p>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="okMsg" class="ok">{{ okMsg }}</p>

    <table>
      <thead>
        <tr>
          <th>帆布间</th>
          <th>库位</th>
          <th>在架布卷</th>
          <th style="width: 320px">新间名</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in lofts" :key="row.id">
          <td>
            <strong v-if="editingId !== row.id">{{ row.name }}</strong>
            <span v-else class="hint">{{ row.name }}</span>
          </td>
          <td>{{ row.location || '—' }}</td>
          <td>{{ row.rollCount }}</td>
          <td>
            <template v-if="editingId === row.id">
              <input
                v-model="draftName"
                type="text"
                maxlength="120"
                style="min-width: 200px; width: 100%"
                @keyup.enter="submitName(row)"
                @keyup.esc="cancelEdit"
              />
              <p v-if="rowError" class="error" style="margin: 6px 0 0">{{ rowError }}</p>
            </template>
            <span v-else class="hint">—</span>
          </td>
          <td>
            <template v-if="editingId === row.id">
              <button
                class="btn"
                type="button"
                :disabled="busyId === row.id"
                @click="submitName(row)"
              >
                确认改名
              </button>
              <button
                class="btn secondary"
                type="button"
                style="margin-left: 8px"
                :disabled="busyId === row.id"
                @click="cancelEdit"
              >
                取消
              </button>
            </template>
            <button v-else class="btn secondary" type="button" @click="startEdit(row)">
              改名
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
