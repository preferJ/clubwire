// 백엔드(FastAPI) 응답 DTO. 필드명은 서버 JSON(camelCase) 그대로.

export type SessionStatus = 'OPEN' | 'CONFIRMED' | 'IN_PROGRESS' | 'CLOSED' | 'CANCELLED'
export type GameStatus = 'READY' | 'RUNNING' | 'PAUSED' | 'FINISHED' | 'CANCELLED'
export type ArticleStatus = 'PENDING' | 'GENERATED' | 'PUBLISHED' | 'REJECTED' | 'FAILED' | 'SUPERSEDED'

export interface Club {
  clubId: number
  clubSlug: string
  clubName: string
  sportType: string
  timezone: string
  isAdmin: boolean
}

/** 와이어 상단 요약 줄 */
export interface ClubSummary {
  year: number
  activeMembers: number
  sessions: number
  articles: number
}

export interface AuthResponse {
  accessToken: string
  tokenType: string
  expiresAt: string
}

export interface Member {
  memberId: number
  name: string
  active: boolean
  joinedAt: string | null
  profileImageUrl: string | null
  displayOrder: number | null
}

export interface PersonRef {
  memberId: number
  name: string
}

export interface SessionListItem {
  sessionId: number
  sessionDate: string
  title: string
  location: string | null
  status: SessionStatus
  teamCount: number | null
  confirmedAt: string | null
  closedAt: string | null
  attendeeCount: number
  guestCount: number
}

export interface TeamMemberView extends PersonRef {
  assignType: 'AUTO' | 'MANUAL'
}

export interface GuestView {
  guestId: number
  name: string
  sessionTeamId?: number | null
}

export interface TeamView {
  sessionTeamId: number
  teamCode: string
  displayName: string
  members: TeamMemberView[]
  guests: GuestView[]
  headcount: number
  avgRatingSnapshot?: number | null
  strengthSnapshot?: number | null
}

export interface TeamScore {
  sessionTeamId: number
  teamCode: string | null
  score: number
}

export interface SessionMatch {
  matchId: number
  gameNo: number
  status: GameStatus
  finalized: boolean
  teamA: TeamScore
  teamB: TeamScore
  winTeamId: number | null
  startedAt: string | null
  finishedAt: string | null
}

export interface SessionDetail extends Omit<SessionListItem, 'attendeeCount' | 'guestCount'> {
  attendees: PersonRef[]
  guests: GuestView[]
  headcount: number
  teams: TeamView[]
  balanceLabel: string | null
  matches: SessionMatch[]
  articleIds?: number[]
}

export interface Generation {
  generationId: number
  sessionId: number
  status: string
  teamCount: number
  algorithmVersion: string
  configVersion: number
  seed: number
  candidateCount: number
  validCandidateCount: number
  toleranceFallback: boolean
  spreadPercent: number
  pairPenalty: number
  balanceLabel: string
  teams: {
    teamCode: string
    headcount: number
    avgRating: number
    strength: number
    pairPenalty: number
    members: PersonRef[]  // 선수별 Rating은 서버가 내보내지 않음
    guests: GuestView[]
  }[]
}

export interface MatchTeam {
  sessionTeamId: number
  teamCode: string | null
  displayName: string | null
  score: number
}

export interface MatchState {
  matchId: number
  sessionId: number
  gameNo: number
  status: GameStatus
  finalized: boolean
  finalizedAt: string | null
  teamA: MatchTeam
  teamB: MatchTeam
  durationSec: number
  elapsedSec: number
  remainingSec: number
  overtimeSec: number
  startedAt: string | null
  pausedAt: string | null
  pausedSeconds: number
  finishedAt: string | null
  endReason: string | null
  autoEnd: boolean
  earlyEndGoals: number | null
  winTeamId: number | null
  version: number
  serverTime: string
}

export interface MatchEventView {
  eventId: number
  matchId: number
  eventType: string
  teamId: number | null
  scorerMemberId: number | null
  scorerName: string | null
  assistMemberId: number | null
  assistName: string | null
  memberId: number | null
  ownGoal: boolean
  guestGoal: boolean
  elapsedSec: number | null
  remainingSec: number | null
  refEventId: number | null
  cancelled: boolean
  memo: string | null
  createdAt: string
}

export interface MatchDetailTeam extends MatchTeam {
  members: PersonRef[]
  guestCount: number
}

export interface MatchDetail extends Omit<MatchState, 'teamA' | 'teamB'> {
  teamA: MatchDetailTeam
  teamB: MatchDetailTeam
  events: MatchEventView[]
}

export interface LiveMatch extends MatchState {
  sessionDate: string
  sessionTitle: string
}

export interface NextSuggestion {
  sessionId: number
  nextGameNo: number
  blockedByMatchId: number | null
  suggestedTeamAId: number
  suggestedTeamBId: number
  teams: {
    sessionTeamId: number
    teamCode: string
    displayName: string
    gamesPlayed: number
    consecutive: number
    lastPlayedGameNo: number | null
  }[]
}

export interface SessionSummary {
  sessionId: number
  status: SessionStatus
  finishedCount: number
  unfinalizedCount: number
  readyCount: number
  activeCount: number
  totalGoals: number
  matches: {
    matchId: number
    gameNo: number
    status: GameStatus
    finalized: boolean
    teamA: string | null
    teamB: string | null
    scoreA: number
    scoreB: number
  }[]
  teamRecords: { sessionTeamId: number; teamCode: string; wins: number; draws: number; losses: number }[]
  topScorers: (PersonRef & { count: number })[]
  topAssists: (PersonRef & { count: number })[]
}

export interface MemberStat {
  memberId: number
  name: string
  active: boolean
  games: number
  wins: number
  draws: number
  losses: number
  winRate: number | null
  goals: number
  assists: number
  ownGoals: number
  titleCount: number
  sessionsAttended: number
  lastPlayedDate: string | null
}

export interface MemberDetail {
  summary: MemberStat
  recentForm: {
    matchId: number
    sessionDate: string
    gameNo: number
    result: 'W' | 'D' | 'L'
    goals: number
    assists: number
  }[]
  frequentTeammates: (PersonRef & { matches: number; wins: number; draws: number; winRate: number | null })[]
  bestWinRateTeammates: (PersonRef & { matches: number; winRate: number | null })[]
  frequentOpponents: (PersonRef & { matches: number; wins: number; losses: number; draws: number })[]
}

export interface Award {
  memberTitleId: number
  titleCode: string
  titleName: string
  memberId: number
  memberName: string | null
  periodStart: string
  periodEnd: string
  sessionId: number | null
  awardMethod: 'MANUAL' | 'AUTO'
  facts: { metric?: string; value?: number; tied?: boolean } | null
  note: string | null
  cancelled: boolean
  createdAt: string
}

export interface TitleType {
  titleTypeId: number
  titleCode: string
  titleName: string
  periodType: 'WEEKLY' | 'SESSION'
  awardMethod: 'MANUAL' | 'AUTO'
  autoRule: string | null
  countsAsMvp: boolean
  active: boolean
  displayOrder: number
}

export interface Article {
  articleId: number
  articleType: 'PRE_MATCH' | 'POST_MATCH' | 'SESSION_RECAP'
  sessionId: number | null
  /** 기사가 속한 일정 날짜(YYYY-MM-DD). 와이어·기록 탭에서 일정별로 묶을 때 사용 */
  sessionDate: string | null
  title: string | null
  summary: string | null
  tags: string[]
  status: ArticleStatus
  publishedAt: string | null
  createdAt: string
  generationNo: number
  parentArticleId: number | null
  modelName?: string
  errorMessage?: string | null
}

export interface InsightPayload {
  id: number
  type: string
  category: string
  importance: number
  subject: PersonRef | null
  facts: Record<string, unknown>
}

export interface ArticleDetail extends Article {
  content: string | null
  usedInsightIds: number[]
  members: PersonRef[]
  requestJson?: { insights?: InsightPayload[] } | null
}

export interface ConfigItem {
  key: string
  value: string | number | boolean
  valueType: 'INT' | 'FLOAT' | 'BOOL' | 'STRING'
  defaultValue: string | number | boolean
  description: string
  choices: string[] | null
}

export interface AssignmentLog {
  logId: number
  action: 'ADD' | 'MOVE' | 'REMOVE'
  memberId: number | null
  guestId: number | null
  fromTeamId: number | null
  toTeamId: number | null
  reason: string | null
  createdAt: string
}

// WebSocket 메시지
export type WsMessage =
  | { type: 'HELLO'; clubId: number; serverTime: string }
  | { type: 'PONG'; serverTime: string }
  | { type: 'MATCH_UPDATED'; matchId: number; sessionId: number; match: MatchState }
  | { type: 'MATCH_EVENT'; matchId: number; sessionId: number; event: MatchEventView }
  | { type: 'SESSION_UPDATED'; sessionId: number; status: SessionStatus }
  | { type: 'TEAMS_UPDATED'; sessionId: number }
  | { type: 'ARTICLE_UPDATED'; articleId: number; status: ArticleStatus }
  | { type: 'TITLE_UPDATED'; memberTitleId: number }
