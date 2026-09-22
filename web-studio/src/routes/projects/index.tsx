import { paginateProjects } from './-search'
import { useState } from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  FolderIcon,
  ArrowUpRightIcon,
  PlusIcon,
  SearchIcon,
} from 'lucide-react'
import { Button } from '#/components/ui/button'
import { Input } from '#/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '#/components/ui/dialog'
import { useAppConnection } from '#/hooks/use-app-connection'
import { listProjects } from '#/lib/projects'
import { ProjectEditor } from './-project-editor'
export const Route = createFileRoute('/projects/')({ component: ProjectList })
function ProjectList() {
  const { identityScopeKey } = useAppConnection()
  return <ProjectListContent key={identityScopeKey} />
}
function ProjectListContent() {
  const { t } = useTranslation('playground')
  const search = Route.useSearch()
  const navigate = Route.useNavigate()
  const { connectionRole } = useAppConnection()
  const canManage = connectionRole === 'admin' || connectionRole === 'root'
  const [creating, setCreating] = useState(false)
  const projects = useQuery({ queryKey: ['projects'], queryFn: listProjects })
  const { total, pages, page, entries } = paginateProjects(
    projects.data ?? [],
    search,
  )
  const listSearch = { ...search, page }
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
          <Button onClick={() => setCreating(true)}>
            <PlusIcon className="size-4" />
            {t('projects.create')}
          </Button>
        )}
      </header>
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full sm:max-w-sm">
          <SearchIcon className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            aria-label={t('projects.search')}
            placeholder={t('projects.search')}
            value={search.q}
            onChange={(e) =>
              void navigate({
                search: { ...search, q: e.target.value, page: 1 },
                replace: true,
              })
            }
          />
        </div>
        <select
          className="h-9 rounded-lg border bg-background px-3 text-sm"
          aria-label={t('projects.statusFilter')}
          value={search.status}
          onChange={(e) =>
            void navigate({
              search: {
                ...search,
                status: e.target.value as typeof search.status,
                page: 1,
              },
              replace: true,
            })
          }
        >
          {(['all', 'active', 'archived'] as const).map((s) => (
            <option key={s} value={s}>
              {t(`projects.${s}`)}
            </option>
          ))}
        </select>
        <span className="text-sm text-muted-foreground sm:ml-auto">
          {t('projects.total', { count: total })}
        </span>
      </div>
      {projects.isLoading ? (
        <p className="py-12 text-center text-muted-foreground">
          {t('explorer.loading')}
        </p>
      ) : projects.error ? (
        <div role="alert" className="rounded-xl border p-6 text-destructive">
          {t('projects.error')}：{projects.error.message}
          <Button
            variant="outline"
            className="ml-3"
            onClick={() => void projects.refetch()}
          >
            {t('projects.retry')}
          </Button>
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {entries.map((project) => (
              <Link
                key={project.project_id}
                to="/projects/$projectId"
                params={{ projectId: project.project_id }}
                search={listSearch}
                className="group flex min-w-0 flex-col gap-4 rounded-xl border border-border/70 bg-card/50 p-5 transition-colors hover:border-primary/30 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div className="flex items-center justify-between">
                  <span className="flex size-10 items-center justify-center rounded-lg border bg-background/50 text-muted-foreground">
                    <FolderIcon className="size-5" />
                  </span>
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs ${project.status === 'active' ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-muted text-muted-foreground'}`}
                  >
                    <span className="size-1.5 rounded-full bg-current" />
                    {t(`projects.${project.status}`)}
                  </span>
                </div>
                <div>
                  <h2 className="truncate text-base font-semibold">
                    {project.name}
                  </h2>
                  <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-muted-foreground">
                    {project.description || t('projects.noDescription')}
                  </p>
                </div>
                <div className="mt-auto flex items-center justify-between gap-2 border-t border-border/50 pt-3 text-xs text-muted-foreground">
                  <code className="truncate">{project.project_id}</code>
                  <ArrowUpRightIcon className="size-4 shrink-0" />
                </div>
              </Link>
            ))}
          </div>
          {!total && (
            <div className="rounded-xl border border-dashed py-16 text-center text-muted-foreground">
              <FolderIcon className="mx-auto mb-3 size-8 opacity-50" />
              {t('projects.empty')}
            </div>
          )}
          <nav
            aria-label={t('projects.pagination')}
            className="flex items-center justify-end gap-3"
          >
            <Button
              variant="outline"
              disabled={page <= 1}
              onClick={() =>
                void navigate({ search: { ...search, page: page - 1 } })
              }
            >
              {t('projects.previous')}
            </Button>
            <span className="text-sm text-muted-foreground">
              {t('projects.page', { page, pages })}
            </span>
            <Button
              variant="outline"
              disabled={page >= pages}
              onClick={() =>
                void navigate({ search: { ...search, page: page + 1 } })
              }
            >
              {t('projects.next')}
            </Button>
          </nav>
        </>
      )}
      <Dialog open={creating && canManage} onOpenChange={setCreating}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('projects.create')}</DialogTitle>
          </DialogHeader>
          <ProjectEditor
            onCreated={(id) => {
              setCreating(false)
              void navigate({
                to: '/projects/$projectId',
                params: { projectId: id },
                search: listSearch,
              })
            }}
          />
        </DialogContent>
      </Dialog>
    </main>
  )
}
