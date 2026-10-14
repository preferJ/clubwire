// A01 관리자 모드 진입: PIN 키패드 바텀시트

import { useState } from 'react'
import { errorMessage } from '../api/client'
import { useClub } from '../lib/club'
import { useToast } from '../lib/toast'
import { Icon } from './Icon'
import { Sheet } from './ui'

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9']

export function PinSheet() {
  const { pinOpen, setPinOpen, login } = useClub()
  const toast = useToast()
  const [pin, setPin] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const close = () => {
    setPinOpen(false)
    setPin('')
    setError(null)
  }
  const press = (d: string) => {
    setError(null)
    setPin((p) => (p.length >= 12 ? p : p + d))
  }
  const submit = async () => {
    setBusy(true)
    try {
      await login(pin)
      toast.show('관리자 모드가 켜졌어요')
      close()
    } catch (e) {
      setError(errorMessage(e))
      setPin('')
    } finally {
      setBusy(false)
    }
  }
  const dots = Math.max(4, pin.length)

  return (
    <Sheet open={pinOpen} onClose={close} labelledBy="pin-title">
      <div className="stack" style={{ alignItems: 'center', gap: 6 }}>
        <span className="avatar" style={{ width: 48, height: 48, background: 'var(--green-soft)', color: 'var(--green)' }}>
          <Icon name="lock" size={22} />
        </span>
        <h2 id="pin-title">관리자 모드</h2>
        <p className="muted" style={{ fontSize: 14 }}>운영진에게 받은 암호를 입력하세요</p>
      </div>
      <div className="pin-dots" aria-label={`입력한 자릿수 ${pin.length}`}>
        {Array.from({ length: dots }).map((_, i) => (
          <span key={i} className={i < pin.length ? 'on' : ''} />
        ))}
      </div>
      {error ? <p className="center" style={{ color: 'var(--warn-ink)', fontSize: 13 }} role="alert">{error}</p> : null}
      <div className="keypad">
        {KEYS.map((k) => (
          <button key={k} type="button" onClick={() => press(k)}>{k}</button>
        ))}
        <span />
        <button type="button" onClick={() => press('0')}>0</button>
        <button type="button" aria-label="지우기" style={{ background: 'transparent' }} onClick={() => setPin((p) => p.slice(0, -1))}>
          <Icon name="del" size={24} />
        </button>
      </div>
      <button type="button" className="btn primary lg block" disabled={pin.length < 4 || busy} onClick={submit}>
        {busy ? '확인 중…' : '관리자 모드 켜기'}
      </button>
      <p className="center small muted">5번 틀리면 5분 동안 입력할 수 없어요</p>
    </Sheet>
  )
}
