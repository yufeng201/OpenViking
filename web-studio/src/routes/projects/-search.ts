export type ProjectSearch = {
  q: string
  status: 'all' | 'active' | 'archived'
  page: number
}
export function parseProjectSearch(
  search: Record<string, unknown>,
): ProjectSearch {
  const page = Number(search.page)
  return {
    q: typeof search.q === 'string' ? search.q : '',
    status:
      search.status === 'active' || search.status === 'archived'
        ? search.status
        : 'all',
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
  }
}

export function paginateProjects<
  T extends {
    name: string
    project_id: string
    description: string
    status: string
  },
>(projects: T[], search: ProjectSearch) {
  const filtered = projects.filter(
    (p) =>
      (search.status === 'all' || p.status === search.status) &&
      `${p.name} ${p.project_id} ${p.description}`
        .toLowerCase()
        .includes(search.q.toLowerCase()),
  )
  const pages = Math.max(1, Math.ceil(filtered.length / 12))
  const page = Math.min(search.page, pages)
  return {
    total: filtered.length,
    pages,
    page,
    entries: filtered.slice((page - 1) * 12, page * 12),
  }
}
