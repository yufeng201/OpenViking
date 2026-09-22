import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { FolderCogIcon } from 'lucide-react'
import { Button } from '#/components/ui/button'
import { Input } from '#/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '#/components/ui/dialog'
import { useAppConnection } from '#/hooks/use-app-connection'
import { listProjects, projectRequest } from '#/lib/projects'
import type { Project } from '#/lib/projects'

export function ProjectManager() {
  const { identityScopeKey } = useAppConnection()
  return <ProjectManagerContent key={identityScopeKey} />
}

function ProjectManagerContent() {
  const { t } = useTranslation('playground')
  const { connectionRole } = useAppConnection()
  const canManage = connectionRole === 'admin' || connectionRole === 'root'
  const [open, setOpen] = useState(false)
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
    enabled: open,
  })
  const members = useQuery({
    queryKey: ['project-members', selected],
    queryFn: () =>
      projectRequest<string[]>(
        'GET',
        `/${encodeURIComponent(selected)}/members`,
      ),
    enabled: open && canManage && !!selected,
  })
  const current = projects.data?.find(
    (project) => project.project_id === selected,
  )
  function select(project?: Project) {
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
    <>
      <Button
        variant="ghost"
        size="icon-sm"
        title={t('projects.title')}
        aria-label={t('projects.title')}
        onClick={() => setOpen(true)}
      >
        <FolderCogIcon className="size-4" />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{t('projects.title')}</DialogTitle>
            <DialogDescription>{t('projects.hint')}</DialogDescription>
          </DialogHeader>
          {projects.isLoading && <p>{t('explorer.loading')}</p>}
          {projects.error && (
            <p role="alert" className="text-destructive">
              {t('projects.error')}：{projects.error.message}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {projects.data?.map((project) => (
              <Button
                disabled={busy}
                key={project.project_id}
                variant={
                  selected === project.project_id ? 'secondary' : 'outline'
                }
                onClick={() => select(project)}
              >
                {project.name} · {t(`projects.${project.status}`)}
              </Button>
            ))}
            {canManage && (
              <Button
                disabled={busy}
                variant="outline"
                onClick={() => select()}
              >
                {t('projects.create')}
              </Button>
            )}
          </div>
          {(canManage || current) && (
            <form
              className="space-y-3"
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
                  }
                })
              }}
            >
              <label className="block space-y-1 text-sm">
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
              <label className="block space-y-1 text-sm">
                <span>{t('projects.name')}</span>
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  disabled={!canManage}
                  required
                />
              </label>
              <label className="block space-y-1 text-sm">
                <span>{t('projects.description')}</span>
                <Input
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  disabled={!canManage}
                />
              </label>
              {canManage && (
                <label className="block space-y-1 text-sm">
                  <span>{t('projects.group')}</span>
                  <Input
                    value={group}
                    onChange={(event) => setGroup(event.target.value)}
                    disabled={!!selected}
                    required
                  />
                  <span className="text-muted-foreground">
                    {t('projects.groupHint')}
                  </span>
                </label>
              )}
              {canManage && (
                <div className="flex gap-2">
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
          {selected && canManage && (
            <section className="space-y-2 border-t pt-3">
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
                <div key={user} className="flex items-center justify-between">
                  <span className="text-sm">{user}</span>
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
                <Input
                  aria-label={t('projects.userId')}
                  placeholder={t('projects.userId')}
                  value={member}
                  onChange={(event) => setMember(event.target.value)}
                  required
                />
                <Button type="submit" disabled={busy}>
                  {t('projects.addMember')}
                </Button>
              </form>
            </section>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {t('projects.error')}：{error}
            </p>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
