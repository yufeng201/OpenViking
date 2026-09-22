import { createFileRoute } from '@tanstack/react-router'
import { ProjectsPage } from './-projects-page'

export const Route = createFileRoute('/projects')({ component: ProjectsPage })
