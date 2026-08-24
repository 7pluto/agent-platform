<script setup lang="ts">
import { computed } from 'vue'
import type { IamSubject } from '../../api'

type Scope = 'PERSONAL' | 'OWNER_DEPT' | 'SELECTED_SUBJECTS'

const props = withDefaults(defineProps<{
  scope: Scope
  subjects: string[]
  users: IamSubject[]
  departments: IamSubject[]
  roles: IamSubject[]
  ownerDeptId?: string
  personalLabel?: string
}>(), { ownerDeptId: '', personalLabel: '仅负责人' })

const emit = defineEmits<{
  'update:scope': [value: Scope]
  'update:subjects': [value: string[]]
  'update:ownerDeptId': [value: string]
}>()

const selected = computed(() => new Set(props.subjects))

function valueOf(type: 'USER' | 'ROLE' | 'DEPT', id: string) { return `${type}:${id}` }
function setScope(scope: Scope) {
  emit('update:scope', scope)
  if (scope === 'PERSONAL') emit('update:subjects', [])
  if (scope === 'OWNER_DEPT') {
    const department = props.ownerDeptId || props.departments[0]?.external_id || ''
    emit('update:ownerDeptId', department)
    emit('update:subjects', department ? [valueOf('DEPT', department)] : [])
  }
}
function setOwnerDepartment(id: string) {
  emit('update:ownerDeptId', id)
  emit('update:subjects', id ? [valueOf('DEPT', id)] : [])
}
function toggle(type: 'USER' | 'ROLE' | 'DEPT', id: string) {
  const value = valueOf(type, id)
  const values = new Set(props.subjects)
  if (values.has(value)) values.delete(value); else values.add(value)
  emit('update:subjects', [...values])
}
</script>

<template>
  <section class="publication-scope-picker">
    <div class="publication-scope-cards">
      <button type="button" :class="{ selected: scope === 'PERSONAL' }" @click="setScope('PERSONAL')"><b>{{ personalLabel }}</b><small>只有发布人可查看和使用</small></button>
      <button type="button" :class="{ selected: scope === 'OWNER_DEPT' }" @click="setScope('OWNER_DEPT')"><b>指定一个部门</b><small>适合部门内部资源和智能体</small></button>
      <button type="button" :class="{ selected: scope === 'SELECTED_SUBJECTS' }" @click="setScope('SELECTED_SUBJECTS')"><b>指定使用对象</b><small>组合用户、角色和部门</small></button>
    </div>
    <label v-if="scope === 'OWNER_DEPT'" class="publication-owner-dept">
      <span>可用部门</span>
      <select :value="ownerDeptId" @change="setOwnerDepartment(($event.target as HTMLSelectElement).value)">
        <option value="">请选择 RuoYi 部门</option>
        <option v-for="item in departments" :key="item.external_id" :value="item.external_id">{{ item.display_name }}</option>
      </select>
    </label>
    <div v-else-if="scope === 'SELECTED_SUBJECTS'" class="publication-subject-groups">
      <section v-for="group in [{ type: 'DEPT' as const, title: '部门', items: departments }, { type: 'ROLE' as const, title: '角色', items: roles }, { type: 'USER' as const, title: '用户', items: users }]" :key="group.type">
        <b>{{ group.title }}</b>
        <div class="publication-subject-cards">
          <button v-for="item in group.items" :key="item.external_id" type="button" :class="{ selected: selected.has(valueOf(group.type, item.external_id)) }" @click="toggle(group.type, item.external_id)"><span>{{ item.display_name }}</span><small>{{ item.external_id }}</small></button>
          <p v-if="!group.items.length" class="empty-copy">暂无可选{{ group.title }}</p>
        </div>
      </section>
    </div>
    <p v-if="scope === 'SELECTED_SUBJECTS'" class="field-hint">已选择 {{ subjects.length }} 个范围；授权按 RuoYi 当前用户、角色和部门身份实时生效。</p>
  </section>
</template>
