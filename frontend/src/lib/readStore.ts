// 소식함 읽음 표시: 연 기사 번호를 브라우저에 기억한다(로그인이 없어 기기·브라우저마다 따로).
// 저장소가 막혀 있으면(사생활 보호 모드 등) 이번 화면에서만 기억한다.

const memory = new Map<string, number[]>()
const key = (slug: string) => `clubwire.read.${slug}`
const MAX = 300

export function readArticleIds(slug: string): Set<number> {
  try {
    const raw = window.localStorage.getItem(key(slug))
    if (raw) return new Set(JSON.parse(raw) as number[])
  } catch {
    /* 저장소 사용 불가 → 메모리 */
  }
  return new Set(memory.get(slug) ?? [])
}

export function markArticleRead(slug: string, articleId: number): void {
  const ids = [...readArticleIds(slug)].filter((x) => x !== articleId)
  ids.push(articleId)
  const kept = ids.slice(-MAX)
  memory.set(slug, kept)
  try {
    window.localStorage.setItem(key(slug), JSON.stringify(kept))
  } catch {
    /* ignore */
  }
}
