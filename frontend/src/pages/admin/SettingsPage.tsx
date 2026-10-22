// 운영 설정(SYSTEM_CONFIG) + 관리자 암호 변경
// 설정 키는 화면에 보여 주지 않는다. 이름·설명은 settingsHelp.ts, (?)를 누르면 자세한 설명이 펼쳐진다.
// 선수별 실력 점수(Rating)는 관리자 화면에서도 보여 주지 않는다(DB에서만 확인).

import { useEffect, useId, useMemo, useState } from 'react'
import type { ConfigItem } from '../../api/types'
import { ErrorBox, Loading, Switch, TopBar } from '../../components/ui'
import { useClub } from '../../lib/club'
import { useAction, useAsync } from '../../lib/hooks'
import { CONFIG_GROUPS, CONFIG_HELP, RATING_GROUP_NOTE, type ConfigHelp } from './settingsHelp'

export function SettingsPage() {
  const { api, slug } = useClub()
  const cfg = useAsync(() => api.config(), [api])
  const { busy, run } = useAction()
  const [draft, setDraft] = useState<Record<string, ConfigItem['value']>>({})
  const [pin, setPin] = useState('')

  useEffect(() => {
    if (cfg.data) setDraft(Object.fromEntries(cfg.data.items.map((i) => [i.key, i.value])))
  }, [cfg.data])

  const grouped = useMemo(() => {
    const items = cfg.data?.items ?? []
    const known = new Set(CONFIG_GROUPS.flatMap((g) => g.keys))
    return CONFIG_GROUPS.map((g) => ({
      ...g,
      // 묶음에 없는 새 설정은 고급 묶음 끝에 붙인다(서버 설명을 이름으로 사용)
      list: [
        ...g.keys.map((k) => items.find((i) => i.key === k)).filter((i): i is ConfigItem => !!i),
        ...(g.advanced ? items.filter((i) => !known.has(i.key)) : []),
      ],
    }))
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
          <details key={g.title} className="card" open={!g.advanced}>
            <summary>{g.title}</summary>
            <div className="stack" style={{ gap: 18 }}>
              {g.advanced ? <p className="small muted" style={{ lineHeight: 1.6 }}>{RATING_GROUP_NOTE}</p> : null}
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
      </main>
      <div className="bar-actions">
        <button type="button" className="btn primary lg block" disabled={busy || Object.keys(changed).length === 0} onClick={save}>
          {Object.keys(changed).length ? `변경 ${Object.keys(changed).length}건 저장` : '변경 사항 없음'}
        </button>
      </div>
    </>
  )
}

/** 설정 한 줄: 이름 + (?) / 입력 / 한 줄 설명 · 기본값 / (?)를 누르면 자세한 설명 */
function ConfigField({ item, value, onChange }: { item: ConfigItem; value: ConfigItem['value'] | undefined; onChange: (v: ConfigItem['value']) => void }) {
  const help: ConfigHelp | undefined = CONFIG_HELP[item.key]
  const label = help?.label ?? item.description
  const [open, setOpen] = useState(false)
  const id = useId()
  const helpId = `${id}-help`
  const helpButton = help ? (
    <button type="button" className="help-btn" aria-label={`${label} 설명`} aria-expanded={open} aria-controls={helpId}
      onClick={() => setOpen((o) => !o)}>?</button>
  ) : null

  let control
  if (item.valueType === 'BOOL') {
    control = null // 스위치는 이름 줄 오른쪽에
  } else if (item.choices) {
    control = (
      <select id={id} className="select" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
        {item.choices.map((c) => <option key={c} value={c}>{help?.choiceLabels?.[c] ?? c}</option>)}
      </select>
    )
  } else {
    control = (
      <div className="row" style={{ gap: 8 }}>
        <input id={id} className="input" type="number" step={item.valueType === 'FLOAT' ? 'any' : 1} value={String(value ?? '')} style={{ flex: 1 }}
          onChange={(e) => onChange(item.valueType === 'INT' ? parseInt(e.target.value || '0', 10) : parseFloat(e.target.value || '0'))} />
        {help?.unit ? <span className="muted" style={{ fontSize: 14, minWidth: 28 }}>{help.unit}</span> : null}
      </div>
    )
  }

  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row between" style={{ gap: 8 }}>
        <span className="row" style={{ gap: 6 }}>
          {item.valueType === 'BOOL'
            ? <b style={{ fontSize: 14 }}>{label}</b>
            : <label htmlFor={id} style={{ fontSize: 14, fontWeight: 700 }}>{label}</label>}
          {helpButton}
        </span>
        {item.valueType === 'BOOL' ? <Switch checked={!!value} onChange={onChange} label={label} /> : null}
      </div>
      {control}
      <span className="small muted" style={{ lineHeight: 1.5 }}>
        {help?.summary ?? ''}
        {help?.summary ? ' ' : ''}
        <span style={{ whiteSpace: 'nowrap' }}>기본값 {fmtValue(item, item.defaultValue)}{item.key === 'MATCH_DURATION_SEC' && value ? ` · 지금 ${Math.round(Number(value) / 60)}분` : ''}</span>
      </span>
      {help && open ? (
        <div id={helpId} className="help-box">
          <p>{help.how}</p>
          <dl>
            {help.effects.map(([when, what]) => (
              <div key={when}><dt>{when}</dt><dd>{what}</dd></div>
            ))}
          </dl>
          {help.tip ? <p className="tip">{help.tip}</p> : null}
        </div>
      ) : null}
    </div>
  )
}

function fmtValue(item: ConfigItem, v: ConfigItem['value']): string {
  const help = CONFIG_HELP[item.key]
  if (item.valueType === 'BOOL') return v ? '켬' : '끔'
  if (item.choices) return help?.choiceLabels?.[String(v)] ?? String(v)
  return `${v}${help?.unit ?? ''}`
}
