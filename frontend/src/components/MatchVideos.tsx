import { useEffect, useRef, useState } from 'react'
import { request, errorMessage } from '../api/client'
import { getAdminToken } from '../lib/authStore'
import { useClub } from '../lib/club'

type Clip = { eventId: number; elapsedSec: number; videoSec: number; startSec: number; endSec: number; skipped?: string; candidates: { videoSec: number; motion: number }[] }
type Video = { videoId: number; status: string; startSec: number; clips: Clip[]; error?: string }

async function binary(slug: string, path: string, file?: File) {
  const response = await fetch(`/api/clubs/${encodeURIComponent(slug)}${path}`, {
    method: file ? 'POST' : 'GET',
    headers: { Authorization: `Bearer ${getAdminToken(slug)}`, ...(file ? { 'Content-Type': 'application/octet-stream' } : {}) },
    body: file,
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(data?.error?.message || '영상 요청에 실패했습니다.')
  }
  return response
}

export function MatchVideos({ matchId }: { matchId: number }) {
  const { slug } = useClub()
  const [videos, setVideos] = useState<Video[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [offset, setOffset] = useState('0')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const base = `/matches/${matchId}/videos`
  useEffect(() => {
    let active = true
    const load = () => request<Video[]>(slug, 'GET', base).then(v => { if (active) setVideos(v) }).catch(e => { if (active) setError(errorMessage(e)) })
    void load()
    const timer = window.setInterval(load, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [slug, base])
  const upload = async () => {
    if (!file) return
    setBusy(true); setError('')
    try {
      const response = await binary(slug, `${base}?start_sec=${Number(offset)}`, file)
      const video = await response.json() as Video
      setVideos(v => [video, ...v.filter(x => x.videoId !== video.videoId)])
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <section className="card stack" style={{ padding: 16 }}>
    <h2>골 장면 찾기 · 실험 기능</h2>
    <p className="small muted">골 기록 전후 30초를 추출하고 움직임이 큰 시점을 추천합니다. 실제 득점 여부는 영상을 보고 확인하세요.</p>
    <p className="small muted">경기 하나의 연속 촬영 영상을 사용하세요. 타이머 일시정지는 보정하지만 촬영 중단·편집 구간은 보정하지 못합니다. 분석 후 원본은 삭제됩니다.</p>
    <label className="field">경기 영상<input type="file" accept="video/*" disabled={busy} onChange={e => setFile(e.target.files?.[0] || null)} /></label>
    <label className="field">영상에서 경기 시작 시점 (초)<input className="input" type="number" min="0" max="14400" step="0.1" value={offset} disabled={busy} onChange={e => setOffset(e.target.value)} /></label>
    <button className="btn primary" disabled={busy || videos.some(v => v.status === 'PROCESSING') || !file || offset === '' || !Number.isFinite(Number(offset)) || Number(offset) < 0 || Number(offset) > 14400} onClick={upload}>{busy ? '영상 업로드 중…' : '업로드하고 골 장면 찾기'}</button>
    {error && <p role="alert">{error}</p>}
    {videos.map(v => <div className="stack" key={v.videoId}>
      <strong>영상 #{v.videoId} · {v.status === 'PROCESSING' ? '분석 대기 / 처리 중' : v.status === 'READY' ? '분석 완료' : '분석 실패'}</strong>
      {v.error && <p role="alert">{v.error}</p>}
      {v.clips.map(c => <div key={c.eventId}><p>골 #{c.eventId} · 경기 {c.elapsedSec}초 / 영상 {c.videoSec}초</p>
        {c.skipped ? <p>{c.skipped}</p> : <ClipPlayer key={`${v.videoId}-${c.eventId}`} slug={slug} path={`${base}/${v.videoId}/clips/${c.eventId}`} clip={c} />}</div>)}
      {v.status !== 'PROCESSING' && <button className="btn" onClick={async () => {
        if (!window.confirm('이 영상의 추출 클립을 삭제할까요? 경기 기록은 유지됩니다.')) return
        try { await request(slug, 'DELETE', `${base}/${v.videoId}`); setVideos(old => old.filter(x => x.videoId !== v.videoId)) }
        catch (e) { setError(errorMessage(e)) }
      }}>추출 영상 삭제</button>}
    </div>)}
  </section>
}

function ClipPlayer({ slug, path, clip }: { slug: string; path: string; clip: Clip }) {
  const player = useRef<HTMLVideoElement>(null)
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])
  const seek = (sec: number) => { if (player.current) player.current.currentTime = Math.max(0, sec - clip.startSec) }
  return <div className="stack">
    {!url ? <button className="btn" disabled={busy} onClick={async () => {
      setBusy(true); setError('')
      try { const r = await binary(slug, path); setUrl(URL.createObjectURL(await r.blob())) }
      catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
    }}>{busy ? '불러오는 중…' : '골 전후 영상 보기'}</button> : <>
      <video ref={player} src={url} controls playsInline preload="metadata" style={{ width: '100%', borderRadius: 12 }} />
      <div className="row" style={{ flexWrap: 'wrap' }}><button className="btn" onClick={() => seek(clip.videoSec)}>기록된 골 시점</button>
        {clip.candidates.map((p, i) => <button className="btn" key={p.videoSec} onClick={() => seek(p.videoSec)}>움직임 후보 {i + 1} · 영상 {p.videoSec}초</button>)}
      </div>
      {!clip.candidates.length && <p className="small muted">뚜렷한 움직임 후보가 없습니다. 기록된 골 시점 주변을 직접 확인하세요.</p>}
    </>}
    {error && <p role="alert">{error}</p>}
  </div>
}
