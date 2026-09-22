import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  FolderCogIcon,
  SearchIcon,
  PlusIcon,
  FolderIcon,
  ArrowUpRightIcon,
  UsersIcon,
  Settings2Icon,
  CodeIcon,
} from 'lucide-react'
import { Link } from '@tanstack/react-router'
import { copyTextToClipboard } from '#/lib/clipboard'
import { getOvResult, ovClient } from '#/lib/ov-client'
import { Button } from '#/components/ui/button'
import { Input } from '#/components/ui/input'
import { useAppConnection } from '#/hooks/use-app-connection'
import { listProjects, projectRequest } from '#/lib/projects'
import type { Project } from '#/lib/projects'

export function ProjectsPage() {
  const { identityScopeKey } = useAppConnection()
  return <ProjectManagerContent key={identityScopeKey} />
}

function ProjectManagerContent() {
  const { t } = useTranslation('playground')
  const { connectionRole, connection } = useAppConnection()
  const canManage = connectionRole === 'admin' || connectionRole === 'root'
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [tab, setTab] = useState('details')
  const [copied, setCopied] = useState(false)
  const [selected, setSelected] = useState('')
  const [id, setId] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [group, setGroup] = useState('')
  const [member, setMember] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const cache = useQueryClient()
  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: listProjects,
  })
  const members = useQuery({
    queryKey: ['project-members', selected],
    queryFn: () =>
      projectRequest<string[]>(
        'GET',
        `/${encodeURIComponent(selected)}/members`,
      ),
    enabled: canManage && !!selected,
  })
  const options = useQuery({
    queryKey: ['project-options', connection.accountId],
    enabled: canManage,
    queryFn: async () => {
      const base = `/api/v1/admin/accounts/${encodeURIComponent(connection.accountId)}`
      const get = <T,>(path: string) =>
        getOvResult<T>(ovClient.instance.get(base + path))
      const [groups, users] = await Promise.all([
        get<Array<{ group_id: string }>>('/groups'),
        get<Array<{ user_id: string }>>('/users?include_credentials=false'),
      ])
      return { groups, users }
    },
  })
  const current = projects.data?.find(
    (project) => project.project_id === selected,
  )
  function select(project?: Project) {
    setCreating(!project)
    setTab('details')
    setCopied(false)
    setMember('')
    setSelected(project?.project_id ?? '')
    setId(project?.project_id ?? '')
    setName(project?.name ?? '')
    setDescription(project?.description ?? '')
    setGroup(project?.group_id ?? '')
    setError('')
  }
  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await action()
      await Promise.all([
        cache.invalidateQueries({ queryKey: ['projects'] }),
        cache.invalidateQueries({ queryKey: ['project-members'] }),
        cache.invalidateQueries({ queryKey: ['viking-fs-ls'] }),
      ])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }
  return (
    <main className="flex w-full min-w-0 flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {t('projects.title')}
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {t('projects.hint')}
          </p>
        </div>
        {canManage && (
          <Button disabled={busy} onClick={() => select()}>
            <PlusIcon className="size-4" />
            {t('projects.create')}
          </Button>
        )}
      </header>
      <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[272px_minmax(0,1fr)]">
        <aside className="min-w-0 space-y-3 rounded-xl border border-border/70 bg-card/50 p-3">
          <div className="relative">
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="bg-background/60 pl-9"
              aria-label={t('projects.search')}
              placeholder={t('projects.search')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {projects.isLoading && <p>{t('explorer.loading')}</p>}
          {projects.error && (
            <p role="alert" className="text-destructive">
              {t('projects.error')}：{projects.error.message}
            </p>
          )}
          <div className="flex flex-col gap-2">
            {projects.data
              ?.filter((project) =>
                `${project.name} ${project.project_id}`
                  .toLowerCase()
                  .includes(search.toLowerCase()),
              )
              .map((project) => (
                <Button
                  className={`h-auto min-h-20 w-full justify-start gap-3 whitespace-normal border px-3 py-3 text-left shadow-none transition-colors ${selected === project.project_id ? 'border-primary/20 bg-primary/5 hover:bg-primary/10' : 'border-transparent hover:border-border/60 hover:bg-muted/60'}`}
                  aria-pressed={selected === project.project_id}
                  disabled={busy}
                  key={project.project_id}
                  variant="ghost"
                  onClick={() => select(project)}
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-background/60 text-muted-foreground">
                    <FolderIcon className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">
                      {project.name}
                    </span>
                    <span className="mt-1 block break-all text-xs text-muted-foreground">
                      <span className="font-mono">{project.project_id}</span>
                      <span className="mt-1.5 flex items-center gap-1.5">
                        <span
                          className={`size-1.5 rounded-full ${project.status === 'active' ? 'bg-emerald-500' : 'bg-muted-foreground/50'}`}
                        />
                        {t(`projects.${project.status}`)}
                      </span>
                    </span>
                  </span>
                </Button>
              ))}
            {!projects.isLoading &&
              !projects.error &&
              !projects.data?.some((project) =>
                `${project.name} ${project.project_id}`
                  .toLowerCase()
                  .includes(search.toLowerCase()),
              ) && (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  {t('projects.empty')}
                </p>
              )}
          </div>
        </aside>
        <section className="min-w-0 space-y-6 rounded-xl border border-border/70 bg-card/50 p-5 md:p-6">
          {!creating && !current && (
            <div className="py-16 text-center text-muted-foreground">
              <FolderCogIcon className="mx-auto mb-4 size-10 opacity-40" />
              <p>{t('projects.selectHint')}</p>
            </div>
          )}
          {(creating || current) && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold">
                    {current?.name ?? t('projects.create')}
                  </h2>
                  {current && (
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                      <code className="rounded-md bg-muted/60 px-2 py-1 text-muted-foreground">
                        {current.project_id}
                      </code>
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 ${current.status === 'active' ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-muted text-muted-foreground'}`}
                      >
                        <span className="size-1.5 rounded-full bg-current" />
                        {t(`projects.${current.status}`)}
                      </span>
                    </div>
                  )}
                </div>
                {current && (
                  <Link
                    className="inline-flex h-9 items-center gap-2 rounded-lg border border-border/70 bg-background/50 px-3 text-sm font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    to="/playground"
                    search={{ uri: `viking://project/${selected}/` }}
                  >
                    {t('projects.browse')}
                    <ArrowUpRightIcon className="size-4 text-muted-foreground" />
                  </Link>
                )}
              </div>
              {current && (
                <nav
                  aria-label={t('projects.sections')}
                  className="flex flex-wrap gap-5 border-b border-border/70"
                >
                  {[
                    'details',
                    ...(canManage ? ['members'] : []),
                    'connect',
                  ].map((value) => (
                    <Button
                      key={value}
                      variant="ghost"
                      aria-pressed={tab === value}
                      className={`-mb-px h-11 rounded-none border-b-2 px-0 hover:bg-transparent ${tab === value ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
                      onClick={() => setTab(value)}
                    >
                      {value === 'details' ? (
                        <Settings2Icon className="size-4" />
                      ) : value === 'members' ? (
                        <UsersIcon className="size-4" />
                      ) : (
                        <CodeIcon className="size-4" />
                      )}
                      {t(`projects.${value}`)}
                    </Button>
                  ))}
                </nav>
              )}
            </>
          )}
          {options.error && (creating || tab === 'members') && (
            <p role="alert" className="text-sm text-destructive">
              {t('projects.error')}：{options.error.message}
            </p>
          )}
          {(creating || current) && tab === 'details' && (
            <form
              className="grid gap-5 sm:grid-cols-2"
              onSubmit={(event) => {
                event.preventDefault()
                void run(async () => {
                  if (selected)
                    await projectRequest(
                      'PATCH',
                      `/${encodeURIComponent(selected)}`,
                      { name, description },
                    )
                  else {
                    await projectRequest('POST', '', {
                      project_id: id,
                      name,
                      description,
                      group_id: group,
                    })
                    setSelected(id)
                    setCreating(false)
                  }
                })
              }}
            >
              <label className="block min-w-0 space-y-2 text-sm">
                <span>{t('projects.id')}</span>
                <Input
                  value={id}
                  onChange={(event) => setId(event.target.value)}
                  disabled={!!selected || !canManage}
                  required
                  pattern="[a-zA-Z0-9_.@-]+"
                  maxLength={128}
                />
              </label>
              <label className="block min-w-0 space-y-2 text-sm">
                <span>{t('projects.name')}</span>
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  disabled={!canManage}
                  required
                />
              </label>
              <label className="block min-w-0 space-y-2 text-sm sm:col-span-2">
                <span>{t('projects.description')}</span>
                <textarea
                  className="min-h-24 w-full resize-y rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 disabled:opacity-50"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  disabled={!canManage}
                />
              </label>
              {canManage && (
                <label className="block min-w-0 space-y-2 text-sm sm:col-span-2">
                  <span>{t('projects.group')}</span>
                  <select
                    className="h-9 w-full rounded-md border bg-background px-3"
                    value={group}
                    onChange={(event) => setGroup(event.target.value)}
                    disabled={!!selected || busy || options.isLoading}
                    required
                  >
                    <option value="">{t('projects.chooseGroup')}</option>
                    {group &&
                      !options.data?.groups.some(
                        (g) => g.group_id === group,
                      ) && <option value={group}>{group}</option>}
                    {options.data?.groups.map((g) => (
                      <option key={g.group_id} value={g.group_id}>
                        {g.group_id}
                      </option>
                    ))}
                  </select>
                  <span className="block text-xs leading-5 text-muted-foreground">
                    {t('projects.groupHint')}
                  </span>
                </label>
              )}
              {canManage && (
                <div className="flex flex-wrap gap-2 border-t border-border/60 pt-5 sm:col-span-2">
                  <Button type="submit" disabled={busy}>
                    {t('projects.save')}
                  </Button>
                  {current && (
                    <Button
                      type="button"
                      variant="outline"
                      disabled={busy}
                      onClick={() =>
                        void run(() =>
                          projectRequest(
                            'PATCH',
                            `/${encodeURIComponent(selected)}`,
                            {
                              status:
                                current.status === 'active'
                                  ? 'archived'
                                  : 'active',
                            },
                          ),
                        )
                      }
                    >
                      {t(
                        current.status === 'active'
                          ? 'projects.archive'
                          : 'projects.restore',
                      )}
                    </Button>
                  )}
                </div>
              )}
            </form>
          )}
          {selected && canManage && tab === 'members' && (
            <section className="space-y-4">
              <h3 className="text-sm font-semibold">{t('projects.members')}</h3>
              <p className="text-xs text-muted-foreground">
                {t('projects.memberHint')}
              </p>
              {members.error && (
                <p role="alert" className="text-destructive">
                  {t('projects.error')}：{members.error.message}
                </p>
              )}
              {members.data?.map((user) => (
                <div
                  key={user}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border/60 bg-background/30 px-4 py-3"
                >
                  <span className="flex min-w-0 items-center gap-3 text-sm">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted font-medium text-muted-foreground">
                      {user.slice(0, 1).toUpperCase()}
                    </span>
                    <span className="truncate">{user}</span>
                  </span>
                  <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() =>
                      void run(() =>
                        projectRequest(
                          'DELETE',
                          `/${encodeURIComponent(selected)}/members/${encodeURIComponent(user)}`,
                        ),
                      )
                    }
                  >
                    {t('projects.remove')}
                  </Button>
                </div>
              ))}
              <form
                className="flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault()
                  void run(async () => {
                    await projectRequest(
                      'PUT',
                      `/${encodeURIComponent(selected)}/members/${encodeURIComponent(member)}`,
                    )
                    setMember('')
                  })
                }}
              >
                <select
                  className="h-9 min-w-0 flex-1 rounded-md border bg-background px-3"
                  aria-label={t('projects.userId')}
                  value={member}
                  onChange={(event) => setMember(event.target.value)}
                  required
                  disabled={
                    busy ||
                    options.isLoading ||
                    !!options.error ||
                    members.isLoading ||
                    !!members.error
                  }
                >
                  <option value="">{t('projects.chooseMember')}</option>
                  {options.data?.users
                    .filter((user) => !members.data?.includes(user.user_id))
                    .map((user) => (
                      <option key={user.user_id} value={user.user_id}>
                        {user.user_id}
                      </option>
                    ))}
                </select>
                <Button type="submit" disabled={busy}>
                  {t('projects.addMember')}
                </Button>
              </form>
            </section>
          )}
          {current && tab === 'connect' && (
            <section className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {t('projects.connectHint')}
              </p>
              <div className="rounded-lg border bg-muted/40 p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <code className="text-sm">.openviking/config.json</code>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={async () => {
                      try {
                        await copyTextToClipboard(
                          JSON.stringify(
                            { version: 2, project_id: selected },
                            null,
                            2,
                          ),
                        )
                        setCopied(true)
                      } catch (reason) {
                        setError(String(reason))
                      }
                    }}
                  >
                    {t(copied ? 'projects.copied' : 'projects.copy')}
                  </Button>
                </div>
                <pre className="overflow-auto text-sm">
                  {JSON.stringify(
                    { version: 2, project_id: selected },
                    null,
                    2,
                  )}
                </pre>
              </div>
              <p className="text-sm text-muted-foreground">
                {t('projects.accessHint')}
              </p>
            </section>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {t('projects.error')}：{error}
            </p>
          )}
        </section>
      </div>
    </main>
  )
}
