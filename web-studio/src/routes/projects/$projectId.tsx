import { createFileRoute, Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowLeftIcon } from 'lucide-react'
import { listProjects } from '#/lib/projects'
import { useAppConnection } from '#/hooks/use-app-connection'
import { Button } from '#/components/ui/button'
import { ProjectEditor } from './-project-editor'
export const Route = createFileRoute('/projects/$projectId')({
  component: ProjectDetail,
})
function ProjectDetail() {
  const { t } = useTranslation('playground')
  const { projectId } = Route.useParams()
  const search = Route.useSearch()
  const { identityScopeKey } = useAppConnection()
  const projects = useQuery({ queryKey: ['projects'], queryFn: listProjects })
  const project = projects.data?.find((p) => p.project_id === projectId)
  return (
    <main className="flex w-full min-w-0 flex-col gap-5">
      <Link
        to="/projects"
        search={search}
        className="inline-flex w-fit items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeftIcon className="size-4" />
        {t('projects.back')}
      </Link>
      {projects.isLoading ? (
        <p>{t('explorer.loading')}</p>
      ) : projects.error ? (
        <div role="alert">
          {t('projects.error')}：{projects.error.message}
          <Button variant="outline" onClick={() => void projects.refetch()}>
            {t('projects.retry')}
          </Button>
        </div>
      ) : project ? (
        <ProjectEditor
          key={`${identityScopeKey}:${projectId}`}
          project={project}
        />
      ) : (
        <div className="rounded-xl border p-12 text-center text-muted-foreground">
          {t('projects.unavailable')}
        </div>
      )}
    </main>
  )
}
