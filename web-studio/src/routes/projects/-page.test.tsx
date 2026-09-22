// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '#/i18n'
import i18n from '#/i18n'
import { ProjectsPage } from './-projects-page'
const mocks = vi.hoisted(() => ({
  role: 'admin',
  request: vi.fn(),
  get: vi.fn(),
}))
vi.mock('#/hooks/use-app-connection', () => ({
  useAppConnection: () => ({
    identityScopeKey: 'test',
    connectionRole: mocks.role,
    connection: { accountId: 'test' },
  }),
}))
vi.mock('@tanstack/react-router', () => ({
  createFileRoute: () => () => ({}),
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}))
vi.mock('#/lib/projects', () => ({
  listProjects: async () => [
    {
      project_id: 'orders',
      name: '订单平台',
      description: 'Shared',
      group_id: 'team',
      status: 'active',
    },
  ],
  projectRequest: mocks.request,
}))
vi.mock('#/lib/ov-client', () => ({
  getOvResult: (p: Promise<unknown>) => p,
  ovClient: { instance: { get: mocks.get } },
}))
beforeEach(async () => {
  mocks.role = 'admin'
  mocks.request.mockResolvedValue(['alice'])
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith('/groups')
      ? [{ group_id: 'team' }]
      : [{ user_id: 'alice' }, { user_id: 'bob' }],
  )
  await i18n.changeLanguage('zh-CN')
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})
function mount() {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ProjectsPage />
    </QueryClientProvider>,
  )
}
it('shows project name, filters existing members and provides repository config', async () => {
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /订单平台/ }))
  await user.click(screen.getByRole('button', { name: '项目成员' }))
  expect(await screen.findByRole('option', { name: 'bob' })).toBeTruthy()
  expect(screen.queryByRole('option', { name: 'alice' })).toBeNull()
  await user.selectOptions(screen.getByRole('combobox'), 'bob')
  await user.click(screen.getByRole('button', { name: '添加成员' }))
  expect(mocks.request).toHaveBeenCalledWith('PUT', '/orders/members/bob')
  await user.click(screen.getByRole('button', { name: 'Agent 接入' }))
  expect(screen.getByText(/"project_id": "orders"/)).toBeTruthy()
})
it('does not expose membership management or account directory APIs to normal users', async () => {
  mocks.role = 'user'
  mount()
  await userEvent.click(await screen.findByRole('button', { name: /订单平台/ }))
  expect(screen.queryByRole('button', { name: '新建项目' })).toBeNull()
  expect(screen.queryByRole('button', { name: '项目成员' })).toBeNull()
  expect(mocks.get).not.toHaveBeenCalled()
  expect(mocks.request).not.toHaveBeenCalled()
})
