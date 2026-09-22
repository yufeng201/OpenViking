import { ovClient, getOvResult, normalizeOvClientError } from '#/lib/ov-client'
import type { VikingFsEntry } from '#/routes/resources/-types/viking-fm'

export interface Project {
  project_id: string
  name: string
  description: string
  group_id: string
  status: 'active' | 'archived'
}
export function projectRequest<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE',
  path = '',
  data?: unknown,
) {
  return getOvResult<T>(
    ovClient.instance.request({
      baseURL: ovClient.getOptions().baseUrl,
      url: `/api/v1/projects${path}`,
      method,
      data,
    }),
  )
}
export const listProjects = () => projectRequest<Project[]>('GET')
export function projectDirectory(
  uri: string,
  name: string,
  abstract = '',
): VikingFsEntry {
  return {
    uri,
    name,
    abstract,
    isDir: true,
    size: '',
    sizeBytes: null,
    modTime: '',
    modTimestamp: null,
  }
}

export async function listProjectsIfSupported(): Promise<Project[]> {
  try {
    return await listProjects()
  } catch (error) {
    if (normalizeOvClientError(error).statusCode === 404) return []
    throw error
  }
}
