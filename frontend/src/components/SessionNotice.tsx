// 일정별 공지 한 덩어리(상시 공지와 별개). 일정 화면 · 메인 팀 편성 카드에서 팀 밸런스 안내 위에 둔다.

/** clamp = 메인 카드용(3줄까지만, 전체는 일정 화면에서) */
export function SessionNotice({ text, clamp }: { text: string | null | undefined; clamp?: boolean }) {
  const notice = text?.trim()
  if (!notice) return null
  return (
    <p className={`session-notice${clamp ? ' clamp' : ''}`} aria-label="일정 공지">
      <b>공지</b>
      <span>{notice}</span>
    </p>
  )
}
