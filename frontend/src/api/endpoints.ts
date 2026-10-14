// 백엔드 API 목록(docs/API.md와 1:1). 화면 코드는 여기 함수만 호출한다.

import { request } from './client'
import type {
  Article,
  ArticleDetail,
  AssignmentLog,
  AuthResponse,
  Award,
  Club,
  ConfigItem,
  Generation,
  LiveMatch,
  MatchDetail,
  MatchEventView,
  MatchState,
  Member,
  MemberDetail,
  MemberStat,
  NextSuggestion,
  RatingRow,
  SessionDetail,
  SessionListItem,
  SessionSummary,
  TitleType,
} from './types'

export const makeApi = (slug: string) => ({
  // 클럽 / 관리자
  club: () => request<Club>(slug, 'GET', ''),
  adminAuth: (password: string) => request<AuthResponse>(slug, 'POST', '/admin/auth', { body: { password } }),
  changePin: (newPassword: string) => request<{ ok: boolean }>(slug, 'POST', '/admin/pin', { body: { newPassword } }),
  config: () => request<{ configVersion: number; items: ConfigItem[] }>(slug, 'GET', '/admin/config'),
  updateConfig: (values: Record<string, unknown>) =>
    request<{ configVersion: number; items: ConfigItem[] }>(slug, 'PATCH', '/admin/config', { body: { values } }),

  // 멤버
  members: (includeInactive = false) => request<Member[]>(slug, 'GET', '/members', { query: { includeInactive } }),
  createMember: (name: string) => request<Member>(slug, 'POST', '/members', { body: { name } }),
  updateMember: (memberId: number, body: Partial<{ name: string; active: boolean; displayOrder: number }>) =>
    request<Member>(slug, 'PATCH', `/members/${memberId}`, { body }),

  // 일정
  sessions: (limit = 30) => request<SessionListItem[]>(slug, 'GET', '/sessions', { query: { limit } }),
  session: (id: number) => request<SessionDetail>(slug, 'GET', `/sessions/${id}`),
  sessionSummary: (id: number) => request<SessionSummary>(slug, 'GET', `/sessions/${id}/summary`),
  createSession: (body: { sessionDate: string; title?: string; location?: string }) =>
    request<SessionDetail>(slug, 'POST', '/sessions', { body }),
  updateSession: (id: number, body: { sessionDate?: string; title?: string; location?: string }) =>
    request<SessionDetail>(slug, 'PATCH', `/sessions/${id}`, { body }),
  cancelSession: (id: number) => request<SessionListItem>(slug, 'POST', `/sessions/${id}/cancel`),
  addAttendees: (id: number, memberIds: number[]) =>
    request<SessionDetail>(slug, 'POST', `/sessions/${id}/members`, { body: { memberIds } }),
  removeAttendee: (id: number, memberId: number) => request(slug, 'DELETE', `/sessions/${id}/members/${memberId}`),
  addGuests: (id: number, count: number) =>
    request<{ guestId: number; name: string }[]>(slug, 'POST', `/sessions/${id}/guests`, { body: { count } }),
  removeGuest: (id: number, guestId: number) => request(slug, 'DELETE', `/sessions/${id}/guests/${guestId}`),
  generateTeams: (id: number, teamCount: number) =>
    request<Generation>(slug, 'POST', `/sessions/${id}/teams/generate`, { body: { teamCount } }),
  confirmTeams: (id: number, generationId: number) =>
    request<SessionDetail>(slug, 'POST', `/sessions/${id}/teams/confirm`, { body: { generationId } }),
  changeAssignment: (
    id: number,
    body: { action: 'ADD' | 'MOVE' | 'REMOVE'; memberId?: number; guestId?: number; guestName?: string; toTeamId?: number; reason?: string },
  ) => request<SessionDetail>(slug, 'POST', `/sessions/${id}/teams/assignments`, { body }),
  assignmentLogs: (id: number) => request<AssignmentLog[]>(slug, 'GET', `/sessions/${id}/teams/assignments`),
  closeSession: (id: number) => request<SessionDetail>(slug, 'POST', `/sessions/${id}/close`),

  // 경기
  live: () => request<LiveMatch[]>(slug, 'GET', '/live'),
  nextSuggestion: (sessionId: number) => request<NextSuggestion>(slug, 'GET', `/sessions/${sessionId}/matches/next-suggestion`),
  createNextMatch: (sessionId: number, teamAId: number, teamBId: number) =>
    request<MatchState>(slug, 'POST', `/sessions/${sessionId}/matches/next`, { body: { teamAId, teamBId } }),
  match: (id: number) => request<MatchDetail>(slug, 'GET', `/matches/${id}`),
  matchAction: (id: number, action: 'start' | 'pause' | 'resume' | 'end' | 'cancel' | 'finalize' | 'unfinalize') =>
    request<MatchState>(slug, 'POST', `/matches/${id}/${action}`),
  addGoal: (
    id: number,
    body: {
      teamId: number
      scorerMemberId?: number | null
      assistMemberId?: number | null
      ownGoal?: boolean
      guestGoal?: boolean
      elapsedSec?: number | null
      idempotencyKey: string
    },
  ) => request<{ eventId: number; duplicate: boolean; match: MatchState }>(slug, 'POST', `/matches/${id}/goals`, { body }),
  cancelGoal: (id: number, eventId: number) =>
    request<{ eventId: number; match: MatchState }>(slug, 'POST', `/matches/${id}/events/${eventId}/cancel`, { body: {} }),
  addMatchMember: (id: number, memberId: number, teamId: number) =>
    request<MatchDetail>(slug, 'POST', `/matches/${id}/members`, { body: { memberId, teamId } }),
  removeMatchMember: (id: number, memberId: number) => request<MatchDetail>(slug, 'DELETE', `/matches/${id}/members/${memberId}`),

  // 통계 / 타이틀
  memberStats: () => request<MemberStat[]>(slug, 'GET', '/stats/members'),
  memberDetail: (id: number) => request<MemberDetail>(slug, 'GET', `/stats/members/${id}`),
  titleTypes: () => request<TitleType[]>(slug, 'GET', '/titles/types'),
  awards: (query: { memberId?: number; from?: string; to?: string } = {}) =>
    request<Award[]>(slug, 'GET', '/titles/awards', { query }),
  award: (body: { titleCode: string; memberId: number; sessionId?: number; note?: string }) =>
    request(slug, 'POST', '/titles/awards', { body }),
  ratings: () => request<RatingRow[]>(slug, 'GET', '/admin/ratings'),

  // The Wire
  articles: (query: { tag?: string; memberId?: number; sessionId?: number; all?: boolean; limit?: number } = {}) =>
    request<Article[]>(slug, 'GET', '/articles', { query }),
  article: (id: number) => request<ArticleDetail>(slug, 'GET', `/articles/${id}`),
  publishArticle: (id: number) => request<ArticleDetail>(slug, 'POST', `/articles/${id}/publish`),
  rejectArticle: (id: number) => request<ArticleDetail>(slug, 'POST', `/articles/${id}/reject`),
  regenerateArticle: (id: number) => request<ArticleDetail>(slug, 'POST', `/articles/${id}/regenerate`),
})

export type Api = ReturnType<typeof makeApi>
export type { MatchEventView }
