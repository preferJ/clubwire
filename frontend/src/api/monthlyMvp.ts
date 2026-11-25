import { request } from './client'

export interface MonthlyMvpSelection {
  month: string
  winners: { memberId: number; name: string }[]
  articleId: number | null
  articleStatus: string | null
}

export const monthlyMvpApi = (slug: string) => ({
  status: (month: string) => request<MonthlyMvpSelection>(slug, 'GET', '/monthly-mvp', { query: { month } }),
  select: (memberId: number, month: string, replace = false) =>
    request<MonthlyMvpSelection & { changed: boolean }>(slug, 'POST', `/members/${memberId}/monthly-mvp`, {
      body: { month, replace },
    }),
})
