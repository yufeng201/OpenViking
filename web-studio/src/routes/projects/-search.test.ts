import { describe, expect, it } from 'vitest'
import { parseProjectSearch, paginateProjects } from './-search'
describe('project list URL state', () => {
  it('retains search, status and page for detail return links', () => {
    expect(
      parseProjectSearch({ q: 'orders', status: 'archived', page: '3' }),
    ).toEqual({ q: 'orders', status: 'archived', page: 3 })
  })
  it.each([-1, 0, 1.5, 'oops', Infinity])('rejects invalid page %s', (page) => {
    expect(parseProjectSearch({ q: [], status: 'unknown', page })).toEqual({
      q: '',
      status: 'all',
      page: 1,
    })
  })
})

it('filters before pagination and clamps a stale page after filtering', () => {
  const data = Array.from({ length: 25 }, (_, i) => ({
    project_id: `p${i}`,
    name: 'Orders',
    description: '',
    status: i === 24 ? 'archived' : 'active',
  }))
  const second = paginateProjects(data, { q: '', status: 'all', page: 2 })
  expect(second.entries.map((p) => p.project_id)).toEqual(
    data.slice(12, 24).map((p) => p.project_id),
  )
  expect(second.pages).toBe(3)
  const archived = paginateProjects(data, {
    q: 'orders',
    status: 'archived',
    page: 3,
  })
  expect(archived).toMatchObject({
    total: 1,
    page: 1,
    pages: 1,
    entries: [{ project_id: 'p24' }],
  })
  expect(
    paginateProjects(data, { q: 'missing', status: 'all', page: 3 }),
  ).toMatchObject({ total: 0, page: 1, pages: 1, entries: [] })
})
