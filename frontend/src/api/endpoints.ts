// 백엔드 API 목록(docs/API.md와 1:1). 화면 코드는 여기 함수만 호출한다.

import { request } from './client'
import type {
  Article,
  AwayOpponentDetail,
  AwayOverview,
  Opponent,
  ArticleDetail,
  AssignmentLog,
  AuthResponse,
  Award,
  Club,
  ClubAppearance,
  ClubAppearanceUpdate,
  ClubContent,
  ClubSummary,
  ConfigItem,
  Generation,
  LiveMatch,
  MatchDetail,
  MatchEventView,
  MatchState,
  Member,
  MemberDetail,
  MemberProfile,
  MemberStat,
  MvpRace,
  NextSuggestion,
  SessionDetail,
  SessionListItem,
  SessionSummary,
  TitleType,
} from './types'

export const makeApi = (slug: string) => ({
  // 클럽 / 관리자
  club: () => request<Club>(slug, 'GET', ''),
  clubAppearance: () => request<ClubAppearance>(slug, 'GET', '/appearance'),
  updateClubAppearance: (body: ClubAppearanceUpdate) =>
    request<ClubAppearance>(slug, 'PATCH', '/admin/appearance', { body }),
  clubSummary: () => request<ClubSummary>(slug, 'GET', '/summary'),
  clubContent: () => request<ClubContent>(slug, 'GET', '/content'),
  updateClubContent: (body: Partial<Pick<ClubContent, 'operatingRules' | 'announcement' | 'announcementSize'>>) =>
    request<ClubContent>(slug, 'PATCH', '/admin/content', { body }),
  adminAuth: (password: string) => request<AuthResponse>(slug, 'POST', '/admin/auth', { body: { password } }),
  changePin: (newPassword: string) => request<{ ok: boolean }>(slug, 'POST', '/admin/pin', { body: { newPassword } }),
  config: () => request<{ configVersion: number; items: ConfigItem[] }>(slug, 'GET', '/admin/config'),
  updateConfig: (values: Record<string, unknown>) =>
    request<{ configVersion: number; items: ConfigItem[] }>(slug, 'PATCH', '/admin/config', { body: { values } }),

  // 멤버
  members: (includeInactive = false) => request<Member[]>(slug, 'GET', '/members', { query: { includeInactive } }),
  createMember: (name: string, initialRating?: number, jerseyNumber?: number | null) =>
    request<Member>(slug, 'POST', '/members', { body: { name, initialRating, jerseyNumber } }),
  updateMember: (memberId: number, body: Partial<{ name: string; active: boolean; displayOrder: number } & MemberProfile>) =>
    request<Member>(slug, 'PATCH', `/members/${memberId}`, { body }),
  /** 삭제한 선수만(관리자) */
  deletedMembers: () => request<Member[]>(slug, 'GET', '/members', { query: { deleted: true } }),
  deleteMember: (memberId: number) => request<Member>(slug, 'DELETE', `/members/${memberId}`),
  restoreMember: (memberId: number) => request<Member>(slug, 'POST', `/members/${memberId}/restore`),

  // 일정
  sessions: (limit = 30, category?: 'upcoming' | 'completed' | 'deleted') =>
    request<SessionListItem[]>(slug, 'GET', '/sessions', { query: { limit, category } }),
  session: (id: number) => request<SessionDetail>(slug, 'GET', `/sessions/${id}`),
  sessionSummary: (id: number) => request<SessionSummary>(slug, 'GET', `/sessions/${id}/summary`),
  createSession: (body: { sessionDate: string; title?: string; location?: string }) =>
    request<SessionDetail>(slug, 'POST', '/sessions', { body }),
  updateSession: (id: number, body: { sessionDate?: string; title?: string; location?: string; opponentId?: number }) =>
    request<SessionDetail>(slug, 'PATCH', `/sessions/${id}`, { body }),
  deleteSession: (id: number) => request<SessionListItem>(slug, 'DELETE', `/sessions/${id}`),
  cancelSession: (id: number) => request<SessionListItem>(slug, 'POST', `/sessions/${id}/cancel`),
  addAttendees: (id: number, memberIds: number[]) =>
    request<SessionDetail>(slug, 'POST', `/sessions/${id}/members`, { body: { memberIds } }),
  removeAttendee: (id: number, memberId: number) => request(slug, 'DELETE', `/sessions/${id}/members/${memberId}`),
  addGuests: (id: number, count: number) =>
    request<{ guestId: number; name: string }[]>(slug, 'POST', `/sessions/${id}/guests`, { body: { count } }),
  removeGuest: (id: number, guestId: number) => request(slug, 'DELETE', `/sessions/${id}/guests/${guestId}`),
  /** teamCount 1 = 원정 경기(참석자 전원이 우리 팀, opponentId = 원정팀 목록에서 고른 팀) */
  generateTeams: (id: number, teamCount: number, opponentId?: number) =>
    request<Generation>(slug, 'POST', `/sessions/${id}/teams/generate`, { body: { teamCount, opponentId } }),
  // 원정팀 목록
  /** includeHidden = 숨긴 팀까지 + 팀별 원정 일정 수(관리자 [원정팀 관리]) */
  opponents: (includeHidden = false) =>
    request<Opponent[]>(slug, 'GET', '/opponents', { query: includeHidden ? { includeHidden } : undefined }),
  /** [직접추가]: 같은 이름(공백 · 대소문자 무시)이 있으면 그 팀을 돌려준다(숨긴 팀이면 다시 보이게) */
  createOpponent: (name: string) => request<Opponent>(slug, 'POST', '/opponents', { body: { name } }),
  /** [원정팀 관리] 이름 수정(지난 원정 일정 표시도 새 이름) · 숨기기(active=false) · 복원 */
  updateOpponent: (opponentId: number, body: { name?: string; active?: boolean }) =>
    request<Opponent>(slug, 'PATCH', `/opponents/${opponentId}`, { body }),
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
  /** memberIds: 원정 경기 출전 선수(우리 팀) */
  createNextMatch: (sessionId: number, teamAId: number, teamBId: number, memberIds?: number[]) =>
    request<MatchState>(slug, 'POST', `/sessions/${sessionId}/matches/next`, { body: { teamAId, teamBId, memberIds } }),
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
  /** 골 수정(확정 전까지 누구나): 고친 뒤의 전체 값. elapsedSec를 비우면 원래 득점 시각 유지 */
  editGoal: (
    id: number,
    eventId: number,
    body: {
      teamId: number
      scorerMemberId?: number | null
      assistMemberId?: number | null
      ownGoal?: boolean
      guestGoal?: boolean
      elapsedSec?: number | null
    },
  ) => request<{ eventId: number; changed: boolean; match: MatchState }>(slug, 'PATCH', `/matches/${id}/events/${eventId}`, { body }),
  cancelGoal: (id: number, eventId: number) =>
    request<{ eventId: number; match: MatchState }>(slug, 'POST', `/matches/${id}/events/${eventId}/cancel`, { body: {} }),
  addMatchMember: (id: number, memberId: number, teamId: number) =>
    request<MatchDetail>(slug, 'POST', `/matches/${id}/members`, { body: { memberId, teamId } }),
  removeMatchMember: (id: number, memberId: number) => request<MatchDetail>(slug, 'DELETE', `/matches/${id}/members/${memberId}`),

  // 통계 / 타이틀
  memberStats: () => request<MemberStat[]>(slug, 'GET', '/stats/members'),
  awayStats: () => request<AwayOverview>(slug, 'GET', '/stats/away'),
  awayOpponent: (opponentId: number) => request<AwayOpponentDetail>(slug, 'GET', `/stats/away/opponents/${opponentId}`),
  memberDetail: (id: number, top = 5) => request<MemberDetail>(slug, 'GET', `/stats/members/${id}`, { query: { top } }),
  mvpRace: () => request<MvpRace>(slug, 'GET', '/stats/mvp-race'),
  titleTypes: () => request<TitleType[]>(slug, 'GET', '/titles/types'),
  awards: (query: { memberId?: number; from?: string; to?: string; titleCode?: string; limit?: number } = {}) =>
    request<Award[]>(slug, 'GET', '/titles/awards', { query }),
  award: (body: { titleCode: string; memberId: number; sessionId?: number; note?: string }) =>
    request(slug, 'POST', '/titles/awards', { body }),

  // The Wire
  articles: (query: { tag?: string; memberId?: number; sessionId?: number; all?: boolean; limit?: number; beforeId?: number } = {}) =>
    request<Article[]>(slug, 'GET', '/articles', { query }),
  article: (id: number) => request<ArticleDetail>(slug, 'GET', `/articles/${id}`),
  updateArticle: (id: number, body: { title: string; summary: string; content: string; usedInsightIds?: number[] }) =>
    request<ArticleDetail>(slug, 'PATCH', `/articles/${id}`, { body }),
  publishArticle: (id: number) => request<ArticleDetail>(slug, 'POST', `/articles/${id}/publish`),
  rejectArticle: (id: number) => request<ArticleDetail>(slug, 'POST', `/articles/${id}/reject`),
  regenerateArticle: (id: number, requiredInsightIds?: number[]) =>
    request<ArticleDetail>(slug, 'POST', `/articles/${id}/regenerate`, {
      body: requiredInsightIds === undefined ? undefined : { requiredInsightIds },
    }),
})

export type Api = ReturnType<typeof makeApi>
export type { MatchEventView }
