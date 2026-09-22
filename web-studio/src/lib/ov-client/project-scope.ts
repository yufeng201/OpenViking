/** Resolve request scope from explicit asset URIs, never from a global last selection. */
export function projectIdFromUri(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  return /^viking:\/\/project\/([^/]+)(?:\/|$)/.exec(value)?.[1]
}

export function projectScopeForRequest(
  params: unknown,
  body: unknown,
): string | undefined {
  const ids = new Set<string>()
  for (const value of [params, body]) {
    if (!value || typeof value !== 'object') continue
    for (const key of [
      'uri',
      'target_uri',
      'root_uri',
      'to',
      'parent',
      'from',
      'from_uri',
      'to_uri',
    ]) {
      const field = (value as Record<string, unknown>)[key]
      for (const item of Array.isArray(field) ? field : [field]) {
        const id = projectIdFromUri(item)
        if (id) ids.add(id)
      }
    }
  }
  if (ids.size > 1)
    throw new Error('A request cannot span multiple project workspaces')
  return ids.values().next().value
}
