import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { monthlyMvpApi } from '../api/monthlyMvp'
import { useClub, useClubEvent } from '../lib/club'
import { useAsync } from '../lib/hooks'
import { useToast } from '../lib/toast'
import { Icon } from './Icon'
import { ErrorBox, Loading, Sheet } from './ui'

function currentMonth() {
  const parts = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit' }).formatToParts(new Date())
  return `${parts.find((p) => p.type === 'year')!.value}-${parts.find((p) => p.type === 'month')!.value}`
}

export function MonthlyMvpPicker({ memberId, name, onSaved }: { memberId: number; name: string; onSaved: () => void }) {
  const [open, setOpen] = useState(false)
  const [month, setMonth] = useState(currentMonth)
  const [busy, setBusy] = useState(false)
  const { slug } = useClub()
  const latest = currentMonth()
  const valid = /^\d{4}-(0[1-9]|1[0-2])$/.test(month) && month >= '0001-01' && month <= latest
  const close = useCallback(() => { if (!busy) setOpen(false) }, [busy])
  return (
    <>
      <button type="button" className="btn primary block" onClick={() => setOpen(true)}>
        <Icon name="trophy" size={18} />이달의 MVP선정
      </button>
      <Sheet open={open} onClose={close} labelledBy="monthly-mvp-title">
        <div className="row between">
          <h2 id="monthly-mvp-title">이달의 MVP선정</h2>
          <button type="button" className="icon-btn" onClick={close} disabled={busy} aria-label="닫기"><Icon name="close" /></button>
        </div>
        <p className="small muted">{name} 선수를 선택한 달의 MVP로 선정합니다. 선정하면 발표 기사를 작성해 게시합니다.</p>
        <label className="field">
          선정할 달
          <input className="input" type="month" value={month} max={latest} required disabled={busy}
            onChange={(e) => setMonth(e.target.value)} aria-invalid={!valid} />
        </label>
        {!valid ? <p className="small" role="alert" style={{ color: 'var(--warn-ink)' }}>이번 달 또는 이전 달을 선택해 주세요.</p>
          : open ? <SelectionForm key={`${slug}-${memberId}-${month}`} memberId={memberId} name={name} month={month} onSaved={onSaved} onBusy={setBusy} /> : null}
      </Sheet>
    </>
  )
}

function SelectionForm({ memberId, name, month, onSaved, onBusy }: {
  memberId: number; name: string; month: string; onSaved: () => void; onBusy: (value: boolean) => void
}) {
  const { slug } = useClub()
  const api = useMemo(() => monthlyMvpApi(slug), [slug])
  const selected = useAsync(() => api.status(month), [api, month])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const toast = useToast()
  const pending = selected.data?.articleStatus === 'PENDING'
  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(selected.reload, 3000)
    return () => window.clearInterval(timer)
  }, [pending, selected.reload])
  useClubEvent((event) => {
    if (event.type === 'TITLE_UPDATED'
      || (event.type === 'ARTICLE_UPDATED' && event.articleId === selected.data?.articleId)
      || event.type === 'RECONNECTED') selected.reload()
  })

  const d = selected.data
  const same = d?.winners.length === 1 && d.winners[0].memberId === memberId
  const submit = async () => {
    if (!d || selected.error || busy) return
    const replace = d.winners.length > 0 && !same
    if (replace && !window.confirm(`${month} MVP(${d.winners.map((w) => w.name).join(', ')})를 ${name} 선수로 변경할까요? 기존 수상과 기사는 이력으로 보관하고 새 발표 기사를 만듭니다.`)) return
    setError(null)
    setBusy(true)
    onBusy(true)
    try {
      const result = await api.select(memberId, month, replace)
      selected.setData(result)
      onSaved()
      toast.show(result.changed ? `${name} 선수를 ${month} MVP로 선정했어요` : '이미 이달의 MVP로 선정된 선수예요')
    } catch (e) {
      setError(e)
      void selected.reload()
    } finally {
      setBusy(false)
      onBusy(false)
    }
  }

  if (selected.error) return <ErrorBox error={selected.error} onRetry={selected.reload} />
  if (!d) return <Loading rows={2} />
  return (
    <div className="stack">
      <div className={`notice ${same ? 'green' : 'gray'}`}>
        {d.winners.length ? `현재 ${month} MVP: ${d.winners.map((w) => w.name).join(', ')}` : '아직 선정된 MVP가 없습니다.'}
      </div>
      {error ? <p className="small" role="alert" style={{ color: 'var(--warn-ink)' }}>{errorMessage(error)}</p> : null}
      <button type="button" className="btn primary lg block" disabled={busy || same} onClick={submit}>
        {busy ? '선정 중…' : same ? '선정 완료' : `${name} 선수 MVP 선정`}
      </button>
      {d.articleId ? (
        <div className="stack" role="status" style={{ gap: 6 }}>
          {pending ? <p className="small muted">MVP 발표 기사를 작성하고 있습니다. 완료되면 자동 게시됩니다.</p> : null}
          {d.articleStatus === 'FAILED' ? <p className="small" style={{ color: 'var(--warn-ink)' }}>MVP 선정은 완료됐지만 기사 작성에 실패했습니다. 기사 관리에서 다시 쓰기를 눌러 주세요.</p> : null}
          {d.articleStatus === 'PUBLISHED'
            ? <Link className="btn block" to={`/c/${slug}/articles/${d.articleId}`}>MVP 기사 보기 <Icon name="chevron" size={16} /></Link>
            : <Link className="btn block" to={`/c/${slug}/admin/articles?articleType=MONTHLY_MVP&articleId=${d.articleId}`}>기사 작성 상태 확인 <Icon name="chevron" size={16} /></Link>}
        </div>
      ) : null}
    </div>
  )
}
