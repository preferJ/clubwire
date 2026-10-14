// 운영 설정(SYSTEM_CONFIG) + 관리자 암호 변경 + Hidden Rating 확인

import { useEffect, useMemo, useState } from 'react'
import type { ConfigItem } from '../../api/types'
import { ErrorBox, Loading, Switch, TopBar } from '../../components/ui'
import { useClub } from '../../lib/club'
import { useAction, useAsync } from '../../lib/hooks'

const GROUPS: { title: string; match: (k: string) => boolean }[] = [
  { title: '경기', match: (k) => k.startsWith('MATCH_') && k !== 'MATCH_RATING_K' },
  { title: '기사(The Wire)', match: (k) => k.startsWith('ARTICLE_') || k.startsWith('WIRE_') },
  { title: '팀 편성', match: (k) => k.startsWith('TEAM_') || k.startsWith('PAIR_') },
  { title: 'Rating · Confidence (고급)', match: () => true },
]

const LABELS: Record<string, string> = {
  MATCH_DURATION_SEC: '경기 시간(초)',
  MATCH_AUTO_END_YN: '시간이 끝나면 자동 종료',
  MATCH_EARLY_END_GOALS: 'N골 먼저 넣으면 조기 종료(0=사용 안 함)',
  ARTICLE_PUBLISH_MODE: '기사 게시 방식',
  WIRE_MAX_INSIGHTS: '기사 1건에 넘기는 사실 최대 개수',
  TEAM_RATING_TOLERANCE_PERCENT: '팀 전력 허용 차이(%)',
  TEAM_CANDIDATE_COUNT: '팀 편성 후보 수',
}

export function SettingsPage() {
  const { api, slug } = useClub()
  const cfg = useAsync(() => api.config(), [api])
  const ratings = useAsync(() => api.ratings(), [api])
  const { busy, run } = useAction()
  const [draft, setDraft] = useState<Record<string, ConfigItem['value']>>({})
  const [pin, setPin] = useState('')

  useEffect(() => {
    if (cfg.data) setDraft(Object.fromEntries(cfg.data.items.map((i) => [i.key, i.value])))
  }, [cfg.data])

  const grouped = useMemo(() => {
    const items = cfg.data?.items ?? []
    const used = new Set<string>()
    return GROUPS.map((g) => {
      const list = items.filter((i) => !used.has(i.key) && g.match(i.key))
      list.forEach((i) => used.add(i.key))
      return { title: g.title, list }
    })
  }, [cfg.data])

  const changed = Object.fromEntries(
    Object.entries(draft).filter(([k, v]) => String(cfg.data?.items.find((i) => i.key === k)?.value) !== String(v)),
  )

  const save = async () => {
    const r = await run(() => api.updateConfig(changed), '설정을 저장했어요')
    if (r) cfg.setData(r)
  }

  if (cfg.error) return <ErrorBox error={cfg.error} onRetry={cfg.reload} />
  if (!cfg.data) return <div className="page"><Loading /></div>

  return (
    <>
      <TopBar title="운영 설정" sub={`설정 버전 ${cfg.data.configVersion}`} back={`/c/${slug}/admin`} />
      <main className="page">
        {grouped.map((g) => g.list.length ? (
          <details key={g.title} className="card" open={!g.title.includes('고급')}>
            <summary>{g.title}</summary>
            <div className="stack" style={{ gap: 12 }}>
              {g.list.map((i) => (
                <ConfigField key={i.key} item={i} value={draft[i.key]} onChange={(v) => setDraft((d) => ({ ...d, [i.key]: v }))} />
              ))}
            </div>
          </details>
        ) : null)}

        <section className="card stack" style={{ gap: 10 }}>
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>관리자 암호 변경</h2>
          <input className="input" type="password" inputMode="numeric" autoComplete="new-password" aria-label="새 암호" placeholder="새 암호(4자 이상)"
            value={pin} onChange={(e) => setPin(e.target.value)} />
          <button type="button" className="btn" disabled={busy || pin.length < 4}
            onClick={async () => { if (await run(() => api.changePin(pin), '암호를 바꿨어요')) setPin('') }}>암호 바꾸기</button>
        </section>

        <details className="card">
          <summary>Hidden Rating 보기(관리자 전용)</summary>
          {ratings.data ? (
            <div className="table-box" style={{ border: 0 }}>
              <table className="data">
                <thead><tr><th>#</th><th>이름</th><th>Rating</th><th>Confidence</th><th>경기</th></tr></thead>
                <tbody>
                  {ratings.data.map((r, i) => (
                    <tr key={r.memberId}><td>{i + 1}</td><td>{r.name}</td><td className="mono">{r.rating.toFixed(1)}</td><td className="mono">{r.confidence.toFixed(2)}</td><td>{r.matchCount}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <Loading rows={1} />}
        </details>
      </main>
      <div className="bar-actions">
        <button type="button" className="btn primary lg block" disabled={busy || Object.keys(changed).length === 0} onClick={save}>
          {Object.keys(changed).length ? `변경 ${Object.keys(changed).length}건 저장` : '변경 사항 없음'}
        </button>
      </div>
    </>
  )
}

function ConfigField({ item, value, onChange }: { item: ConfigItem; value: ConfigItem['value'] | undefined; onChange: (v: ConfigItem['value']) => void }) {
  const label = LABELS[item.key] ?? item.description
  if (item.valueType === 'BOOL') {
    return (
      <div className="row between">
        <span className="stack" style={{ gap: 0 }}><b style={{ fontSize: 14 }}>{label}</b><span className="small muted">{item.key}</span></span>
        <Switch checked={!!value} onChange={onChange} label={label} />
      </div>
    )
  }
  if (item.choices) {
    return (
      <label className="field">{label}
        <select className="select" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
          {item.choices.map((c) => <option key={c} value={c}>{c === 'MANUAL' ? 'MANUAL (관리자 검토 후 게시)' : c === 'AUTO' ? 'AUTO (생성 즉시 게시)' : c}</option>)}
        </select>
      </label>
    )
  }
  return (
    <label className="field">
      <span>{label}{item.key === 'MATCH_DURATION_SEC' && value ? ` · ${Math.round(Number(value) / 60)}분` : ''}</span>
      <input className="input" type="number" step={item.valueType === 'FLOAT' ? 'any' : 1} value={String(value ?? '')}
        onChange={(e) => onChange(item.valueType === 'INT' ? parseInt(e.target.value || '0', 10) : parseFloat(e.target.value || '0'))} />
      <span className="small" style={{ fontWeight: 400 }}>{item.key} · 기본 {String(item.defaultValue)}{LABELS[item.key] ? ` · ${item.description}` : ''}</span>
    </label>
  )
}
