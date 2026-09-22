import { createFileRoute, Outlet } from '@tanstack/react-router'
import { parseProjectSearch } from './-search'
export const Route = createFileRoute('/projects')({
  validateSearch: parseProjectSearch,
  component: Outlet,
})
