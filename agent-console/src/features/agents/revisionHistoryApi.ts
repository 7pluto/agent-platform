export interface RevisionDependencySnapshot {
  version_id: string
  resource_id: string
  resource_type: string
  display_name: string
  version_number: number
  content_hash: string
}

export interface RevisionCapabilitySnapshot {
  version_id: string
  resource_id: string
  resource_type: string
  display_name: string
  version_number: number
  content_hash: string
  dependencies: RevisionDependencySnapshot[]
}

export interface RevisionPublicationSnapshot {
  available: boolean
  scope?: string | null
  subjects: Array<{ subject_type: string; subject_id: string }>
}

export interface RevisionHistoryItem {
  revision_id: string
  revision_number: number
  agent_version_id: string
  agent_version_number: number
  created_by: string
  created_at: string
  active: boolean
  capabilities: RevisionCapabilitySnapshot[]
  publication: RevisionPublicationSnapshot
}

export async function fetchRevisionHistory(deploymentId: string): Promise<RevisionHistoryItem[]> {
  const response = await fetch(`/api/v1/workbench/deployments/${deploymentId}/revision-history`, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  })
  const payload = await response.json().catch(() => ({})) as RevisionHistoryItem[] | { message?: string; code?: string }
  if (!response.ok) {
    const error = payload as { message?: string; code?: string }
    throw new Error(error.message || error.code || `HTTP ${response.status}`)
  }
  return payload as RevisionHistoryItem[]
}
