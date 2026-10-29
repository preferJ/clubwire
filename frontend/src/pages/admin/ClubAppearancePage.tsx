import { useEffect, useRef, useState } from 'react'
import { errorMessage } from '../../api/client'
import type { ClubAppearance, CrestConfig, ThemeMode } from '../../api/types'
import { Crest } from '../../components/ClubCrest'
import { ErrorBox, Loading, TopBar } from '../../components/ui'
import { useClub } from '../../lib/club'
import { useAction } from '../../lib/hooks'
import './club-appearance.css'

const DEFAULT_CREST: CrestConfig = {
  mode: 'auto', shape: 'shield', pattern: 'stripes', primaryColor: '#c81e2b',
  secondaryColor: '#ffffff', textColor: '#ffffff', text: '', symbol: 'none',
}
const CREST_KEYS = Object.keys(DEFAULT_CREST) as (keyof CrestConfig)[]
const MAX_IMAGE_BYTES = 2 * 1024 * 1024
const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp']

function sameCrest(a: CrestConfig, b: CrestConfig) {
  return CREST_KEYS.every((key) => a[key] === b[key])
}

function readImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('이미지를 읽지 못했어요.'))
    reader.onerror = () => reject(new Error('이미지를 읽지 못했어요. 다른 파일을 선택해 주세요.'))
    reader.readAsDataURL(file)
  })
}

export function ClubAppearancePage() {
  const { api, slug, club, refreshClub } = useClub()
  const [attempt, setAttempt] = useState(0)
  const [initial, setInitial] = useState<ClubAppearance | null>(null)
  const [crest, setCrest] = useState<CrestConfig>(DEFAULT_CREST)
  const [defaultTheme, setDefaultTheme] = useState<ThemeMode>('dark')
  // undefined는 기존 이미지를 유지한다. null만 명시적인 삭제다.
  const [imageDraft, setImageDraft] = useState<string | null | undefined>(undefined)
  const [loadError, setLoadError] = useState<unknown>()
  const [saveError, setSaveError] = useState('')
  const [fileError, setFileError] = useState('')
  const [previewError, setPreviewError] = useState('')
  const [imageReady, setImageReady] = useState(false)
  const [reading, setReading] = useState(false)
  const fileSequence = useRef(0)
  const { busy, run } = useAction()

  const hydrate = (saved: ClubAppearance) => {
    setInitial(saved)
    setCrest({ ...saved.crest })
    setDefaultTheme(saved.defaultTheme)
    setImageDraft(undefined)
    setFileError('')
    setSaveError('')
  }

  useEffect(() => {
    let alive = true
    setInitial(null)
    setLoadError(undefined)
    setSaveError('')
    void api.clubAppearance().then((saved) => {
      if (alive) hydrate(saved)
    }).catch((error: unknown) => { if (alive) setLoadError(error) })
    return () => { alive = false; fileSequence.current += 1 }
  }, [api, attempt])

  const imageUrl = imageDraft === undefined ? initial?.imageUrl ?? null : imageDraft
  useEffect(() => {
    setImageReady(false)
    setPreviewError('')
    if (crest.mode !== 'image' || !imageUrl) return
    let alive = true
    const image = new Image()
    image.onload = () => {
      if (!alive) return
      if (image.naturalWidth > 4096 || image.naturalHeight > 4096 || image.naturalWidth * image.naturalHeight > 16_000_000) {
        setPreviewError('이미지는 가로·세로 4096px 이하, 총 1600만 화소 이하로 선택해 주세요.')
      } else if (image.naturalWidth > 0 && image.naturalHeight > 0) setImageReady(true)
      else setPreviewError('이미지를 표시할 수 없어요. 다른 파일을 선택해 주세요.')
    }
    image.onerror = () => { if (alive) setPreviewError('이미지를 표시할 수 없어요. 다른 파일을 선택해 주세요.') }
    image.src = imageUrl
    return () => { alive = false; image.onload = null; image.onerror = null }
  }, [crest.mode, imageUrl])

  const crestChanged = initial !== null && !sameCrest(crest, initial.crest)
  // 기본 마크 복원은 현재 공개 URL이 없어도 남아 있을 수 있는 이전 이미지를 지운다.
  const imageChanged = initial !== null && imageDraft !== undefined
    && (imageDraft === null || (crest.mode === 'image' && imageDraft !== initial.imageUrl))
  const themeChanged = initial !== null && defaultTheme !== initial.defaultTheme
  const changed = crestChanged || imageChanged || themeChanged
  const imageInvalid = crest.mode === 'image' && (!imageUrl || !imageReady || !!previewError)
  const canSave = changed && !busy && !reading && !fileError && !imageInvalid
  const preview: ClubAppearance | null = initial ? { ...initial, crest, imageUrl, defaultTheme } : null
  const teamName = club?.clubName ?? slug

  const updateCrest = <K extends keyof CrestConfig>(key: K, value: CrestConfig[K]) => {
    setSaveError('')
    setCrest((current) => ({ ...current, [key]: value }))
  }

  const resetAuto = () => {
    fileSequence.current += 1
    setReading(false)
    setCrest({ ...DEFAULT_CREST })
    setImageDraft(null)
    setFileError('')
    setSaveError('')
  }

  const chooseMode = (mode: CrestConfig['mode']) => {
    if (mode === 'auto') return resetAuto()
    setFileError('')
    setSaveError('')
    setCrest((current) => ({ ...current, mode,
      ...(mode === 'design' && current.mode === 'auto' ? { text: [...teamName.trim().toUpperCase()].slice(0, 6).join('') } : {}),
    }))
  }

  const chooseImage = async (file: File | undefined) => {
    if (!file) return
    const sequence = ++fileSequence.current
    setReading(false)
    setFileError('')
    if (!IMAGE_TYPES.includes(file.type)) {
      setFileError('PNG, JPG, WebP 이미지 파일만 선택할 수 있어요.')
      return
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setFileError('이미지는 2MB 이하로 선택해 주세요.')
      return
    }
    setReading(true)
    try {
      const dataUrl = await readImage(file)
      if (sequence !== fileSequence.current) return
      setImageDraft(dataUrl)
      setCrest((current) => ({ ...current, mode: 'image' }))
      setSaveError('')
    } catch (error) {
      if (sequence === fileSequence.current) setFileError(errorMessage(error))
    } finally {
      if (sequence === fileSequence.current) setReading(false)
    }
  }

  const discard = () => {
    if (!initial) return
    fileSequence.current += 1
    setReading(false)
    hydrate(initial)
  }

  const save = async () => {
    if (!initial || !canSave) return
    setSaveError('')
    const body = {
      ...(crestChanged ? { crest } : {}),
      ...(imageChanged ? { imageDataUrl: imageDraft } : {}),
      ...(themeChanged ? { defaultTheme } : {}),
    }
    const saved = await run(async () => {
      try { return await api.updateClubAppearance(body) }
      catch (error) { setSaveError(errorMessage(error)); throw error }
    }, '팀 마크와 기본 테마를 저장했어요')
    if (!saved) return
    hydrate(saved)
    try { await refreshClub() }
    catch { setSaveError('설정은 저장됐어요. 화면에 반영되지 않으면 새로고침해 주세요.') }
  }

  return (
    <>
      <TopBar title="팀 마크 · 테마" back={`/c/${slug}/admin`} />
      {loadError ? <ErrorBox error={loadError} onRetry={() => setAttempt((n) => n + 1)} /> : !initial ? (
        <main className="page"><Loading /></main>
      ) : (
        <main className="page appearance-editor">
          <section className="card stack" style={{ gap: 12 }}>
            <div className="row between"><h2>마크 미리보기</h2><span className="small muted">저장 전 미리보기</span></div>
            <div className="appearance-previews">
              {(['dark', 'light'] as const).map((theme) => (
                <div key={theme} className="appearance-preview" data-theme={theme}>
                  <span className="appearance-preview-label">{theme === 'dark' ? '어두운 화면' : '밝은 화면'}</span>
                  <Crest name={teamName} size={82} appearance={preview} />
                  <b>{teamName}</b>
                </div>
              ))}
            </div>
          </section>

          <fieldset className="card appearance-fields" disabled={busy || reading}>
            <legend>팀 마크</legend>
            <div className="appearance-mode-grid" role="group" aria-label="팀 마크 방식">
              {([['auto', '기본 마크'], ['design', '직접 만들기'], ['image', '이미지 등록']] as const).map(([mode, label]) => (
                <button key={mode} type="button" className={`btn sm ${crest.mode === mode ? 'primary' : ''}`}
                  aria-pressed={crest.mode === mode} onClick={() => chooseMode(mode)}>{label}</button>
              ))}
            </div>
            {crest.mode === 'auto' ? (
              <p className="small muted">팀 이름을 넣은 기본 방패 마크를 사용합니다.</p>
            ) : crest.mode === 'design' ? (
              <>
                <div className="appearance-form-grid">
                  <label className="field">모양
                    <select className="input" value={crest.shape} onChange={(e) => updateCrest('shape', e.target.value as CrestConfig['shape'])}>
                      <option value="shield">방패</option><option value="circle">원형</option><option value="rounded">둥근 사각형</option>
                    </select>
                  </label>
                  <label className="field">무늬
                    <select className="input" value={crest.pattern} onChange={(e) => updateCrest('pattern', e.target.value as CrestConfig['pattern'])}>
                      <option value="solid">단색</option><option value="stripes">세로 줄무늬</option><option value="diagonal">대각선</option>
                    </select>
                  </label>
                </div>
                <div className="appearance-color-grid">
                  {([['primaryColor', '바탕색'], ['secondaryColor', '무늬·테두리'], ['textColor', '글자·심볼']] as const).map(([key, label]) => (
                    <label key={key} className="field">{label}
                      <input className="appearance-color" type="color" value={crest[key]} onChange={(e) => updateCrest(key, e.target.value)} />
                      <span className="appearance-color-value">{crest[key].toUpperCase()}</span>
                    </label>
                  ))}
                </div>
                <div className="appearance-form-grid">
                  <label className="field">마크 글자 (최대 6자)
                    <input className="input" value={crest.text} onChange={(e) => updateCrest('text', [...e.target.value].slice(0, 6).join(''))}
                      placeholder="예: YPR" autoComplete="off" />
                  </label>
                  <label className="field">심볼
                    <select className="input" value={crest.symbol} onChange={(e) => updateCrest('symbol', e.target.value as CrestConfig['symbol'])}>
                      <option value="none">없음</option><option value="ball">축구공</option><option value="star">별</option>
                    </select>
                  </label>
                </div>
              </>
            ) : (
              <>
                <label className="field">마크 이미지 선택
                  <input className="appearance-file" type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => {
                    const file = e.target.files?.[0]
                    e.target.value = ''
                    void chooseImage(file)
                  }} />
                </label>
                <p className="small muted">PNG·JPG·WebP, 최대 2MB·4096px·1600만 화소. 투명 배경도 사용할 수 있어요. 이미지는 저장할 때 반영됩니다.</p>
                {!imageUrl ? <p className="small muted">미리 볼 이미지를 선택해 주세요.</p> : !imageReady && !previewError ? <p className="small muted" role="status">이미지를 확인하고 있어요…</p> : null}
                <button type="button" className="btn sm" onClick={resetAuto}>이미지 지우고 기본 마크 사용</button>
              </>
            )}
            {reading ? <p className="small muted" role="status">이미지를 읽고 있어요…</p> : null}
            {fileError || previewError ? <p className="appearance-error" role="alert">{fileError || previewError}</p> : null}
          </fieldset>

          <fieldset className="card appearance-fields" disabled={busy}>
            <legend>팀 기본 테마</legend>
            <p className="small muted">개인 테마를 선택하지 않은 방문자에게 적용됩니다. 각자 고른 화면 테마는 그대로 유지돼요.</p>
            <div className="appearance-theme-grid" role="group" aria-label="팀 기본 테마">
              {([['dark', '어두운 테마'], ['light', '밝은 테마']] as const).map(([theme, label]) => (
                <button type="button" key={theme} className={`btn ${defaultTheme === theme ? 'primary' : ''}`}
                  aria-pressed={defaultTheme === theme} onClick={() => { setDefaultTheme(theme); setSaveError('') }}>{label}</button>
              ))}
            </div>
          </fieldset>
          {saveError ? <p className="appearance-error" role="alert">{saveError}</p> : null}
        </main>
      )}
      {initial ? <div className="bar-actions">
        <button type="button" className="btn primary lg block" disabled={!canSave} onClick={save}>
          {busy ? '저장 중…' : changed ? '변경 사항 저장' : '변경 사항 없음'}
        </button>
        {changed ? <button type="button" className="btn sm block" disabled={busy} onClick={discard}>변경 취소</button> : null}
      </div> : null}
    </>
  )
}
