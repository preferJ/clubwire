/**
 * YPR 안내 원문: https://hesse429.github.io/YPR/
 * 정적 안내·기본 수칙 출처 커밋: 63804e179ce75a223ea44d317eca14ecc7430191
 * 기본 수칙(2026-06-08)은 오프라인 대체본이며, 최신 운영 수칙은 공개 문서를 읽어 온다.
 */
export const YPR_SOURCE_URL = 'https://hesse429.github.io/YPR/'
export const YPR_SOURCE_COMMIT = '63804e179ce75a223ea44d317eca14ecc7430191'
export const YPR_RULES_URL = 'https://firestore.googleapis.com/v1/projects/yprsystem/databases/(default)/documents/mom_data/mom_team_rules'
export const YPR_DEFAULT_RULES_UPDATED_AT = '2026-06-08'

export interface YprRules {
  text: string
  updatedAt: string
}

export const YPR_DEFAULT_RULES_TEXT = `# 1. 팀 운영
## 1.1 운영진 구성
- 회장 이종훈 · 부회장 김동근 · 총무 변현우 (총 3인)

## 1.2 회원 인적사항 공유
- 단체 채팅방 게시판에 이름·나이·전화번호를 예외 없이 게시합니다.

## 1.3 운영진 교체 주기
- 1년 주기로 교체하며, 연말까지 지원자가 없으면 기존 운영진이 연임합니다.

## 1.4 물/음료 준비
- 경기 당일 담당자(운영진 1인)는 회비 5,000원을 감면받습니다.

## 1.5 노쇼 규정
- 사전 통보 없는 불참(노쇼) 2회 시 방출 (매년 1월 1일 갱신)

## 1.6 지각 규정
- 구장 예약시간 이후 도착은 지각 (10분 전 도착 권장)
- 8~9시 도착 1만원 / 9~10시 도착 2만원 / 불참 3만원 (참석 투표 후 적용)
- 지각 5회 시 퇴출 (매년 1월 1일 갱신)

## 1.7 참석 투표 공유
- 최신화될 때마다 단체 채팅방에 실시간 공유합니다.

## 1.8 팀 비품 관리
- 남은 회비로 비품(파스·공·펌프·가방·호루라기·조끼 등)을 구매하며 운영진이 관리합니다.

## 1.9 유니폼/로고 제작
- 제작 여부는 잠정 유보 상태입니다.

## 1.10 회비 규정
- 회비 3만원, 전월 25일까지 납부. 신규 가입자는 가입월은 용병비, 익월부터 회비 납부합니다.

## 1.11 중도 탈퇴 및 환불
- 기납부 회비는 환불되지 않으며, 예외 사유는 운영진 심의로 결정합니다.

## 1.12 휴면
- 연 최대 4개월 가능 (매년 1월 1일 갱신), 초과 시 탈퇴 처리. 휴면 중 참가 시 참가비 15,000원.

## 1.13 회식 규정
- 회식비는 전액 회비 지원, 참석은 자율, 일정은 3주 전 공지합니다.

# 2. 경기 운영
## 2.1 참석 인원별 경기 방식
- 12명 이하: 2팀 경기 (10분 경기 / 2분 휴식)
- 13명 이상: 3팀 경기 (쿼터당 12분 / 1분 휴식 / 팀당 2쿼터 후 휴식 / 골키퍼 쿼터당 1명, 경기 중 자유교체)

## 2.2 팀원 간 플레이 요청
- 운영진에게 개별 요청 후 회의를 통해 결정합니다.

## 2.3 심판 배정
- 운영진 1명이 심판을 담당하며, 운영진이 경기 중이면 휴식 중인 회원이 대신합니다.

## 2.4 경기 규정
- 선수·포지션 교체 제한 없음
- 킥인은 무릎 아래로만
- 킥인 후 터치 없이 골라인 통과 시 골 인정 안 됨
- 천장 맞으면 가까운 사이드라인에서 킥인
- 상대 몸 맞고 사이드아웃 시 킥인 / 골라인아웃 시 코너킥
- 상대 페널티박스 안 파울 시 페널티킥
- 킥인·코너킥 시 상대는 3m 거리 유지
- 중앙선 뒤에서 찬 공이 터치 없이 골라인 통과 시 골 인정 안 됨
- 골키퍼는 자기 진영에서 공을 최초 1회만 받을 수 있음 (위반 시 터치 지점에서 간접 프리킥)

# 3. 구장 예약
## 3.2 예약 성공 혜택
- 예약 성공 회원은 회비 1만원을 환급받습니다.

## 3.3 예약 참여 독려
- 특정 회원에게 부담이 몰리지 않도록 참여 혜택을 제공합니다.
`

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('운영 수칙 형식이 올바르지 않습니다.')
  return value as Record<string, unknown>
}

/** Firestore의 공개 stringValue 안에 저장된 JSON만 읽으며 다른 문서는 조회하지 않는다. */
export function parseYprRulesResponse(response: unknown): YprRules {
  const value = object(object(object(response).fields).value).stringValue
  if (typeof value !== 'string') throw new Error('운영 수칙 내용이 없습니다.')
  const data = object(JSON.parse(value))
  if (typeof data.text !== 'string' || !data.text.trim() || data.text.length > 100000
    || typeof data.updatedAt !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(data.updatedAt)
    || !Number.isFinite(Date.parse(data.updatedAt))) throw new Error('운영 수칙 형식이 올바르지 않습니다.')
  return { text: data.text, updatedAt: data.updatedAt }
}

/** 읽기 전용 GET. 닫기·화면 이동 시 취소하며, 6초를 넘기면 기본 수칙을 표시할 수 있도록 실패한다. */
export async function fetchYprRules(signal?: AbortSignal, fetcher: typeof fetch = fetch): Promise<YprRules> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (signal?.aborted) controller.abort()
  else signal?.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(abort, 6000)
  try {
    const response = await fetcher(YPR_RULES_URL, { method: 'GET', signal: controller.signal, credentials: 'omit' })
    if (!response.ok) throw new Error('운영 수칙을 불러오지 못했습니다.')
    return parseYprRulesResponse(await response.json())
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}

export type GuideTextBlock = { kind: 'heading' | 'subheading' | 'paragraph'; text: string } | { kind: 'list'; items: string[] }

/** # / ## / - 만 해석한다. HTML·스크립트·링크를 실행하거나 삽입하지 않는다. */
export function parseGuideText(text: string): GuideTextBlock[] {
  const blocks: GuideTextBlock[] = []
  for (const line of text.split(/\r?\n/)) {
    const s = line.trim()
    if (!s) continue
    if (s.startsWith('## ')) blocks.push({ kind: 'subheading', text: s.slice(3) })
    else if (s.startsWith('# ')) blocks.push({ kind: 'heading', text: s.slice(2) })
    else if (s.startsWith('- ')) {
      const last = blocks[blocks.length - 1]
      if (last?.kind === 'list') last.items.push(s.slice(2))
      else blocks.push({ kind: 'list', items: [s.slice(2)] })
    } else blocks.push({ kind: 'paragraph', text: s })
  }
  return blocks
}
