import { describe, expect, it } from 'vitest'
import { projectScopeForRequest } from './project-scope'

describe('project request scope', () => {
  it('scopes reads, writes, uploads and retrieval by explicit URI', () => {
    expect(
      projectScopeForRequest(
        { uri: 'viking://project/orders/sessions/s/messages.jsonl' },
        null,
      ),
    ).toBe('orders')
    expect(
      projectScopeForRequest(null, {
        uri: 'viking://project/orders/memories/a.md',
      }),
    ).toBe('orders')
    expect(
      projectScopeForRequest(null, {
        parent: 'viking://project/orders/resources/',
      }),
    ).toBe('orders')
    expect(
      projectScopeForRequest(null, {
        target_uri: ['viking://project/orders/memories', 'viking://resources'],
      }),
    ).toBe('orders')
  })
  it('does not carry the previous project into personal requests', () => {
    projectScopeForRequest({ uri: 'viking://project/orders/resources/' }, null)
    expect(
      projectScopeForRequest({ uri: 'viking://user/alice' }, null),
    ).toBeUndefined()
    expect(
      projectScopeForRequest({ uri: 'viking://project/' }, null),
    ).toBeUndefined()
  })
  it('rejects ambiguous cross-project requests', () => {
    expect(() =>
      projectScopeForRequest(null, {
        target_uri: ['viking://project/a', 'viking://project/b'],
      }),
    ).toThrow()
  })
})
