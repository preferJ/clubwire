import { useId, useState } from 'react'
import type { ClubAppearance, CrestConfig } from '../api/types'

const AUTO_SHIELD = 'M20 2 L37 7 V22 C37 33 30 40 20 44 C10 40 3 33 3 22 V7 Z'
const SHIELD = 'M50 3 L94 16 V54 C94 80 77 98 50 108 C23 98 6 80 6 54 V16 Z'

/** 기본 마크는 기존 방패를 유지하며 밝은 테마에서도 이름 띠가 읽히게 한다. */
function AutoCrest({ name, size }: { name: string; size: number }) {
  const short = name.trim()
  const label = (short.length <= 4 ? short : short.slice(0, 3)).toUpperCase()
  return (
    <svg width={size} height={(size * 46) / 40} viewBox="0 0 40 46" role="img" aria-label={`${short} 엠블럼`} style={{ flex: 'none' }}>
      <path d={AUTO_SHIELD} fill="#fff" />
      <rect x="7" y="8" width="5" height="26" style={{ fill: 'var(--accent)' }} />
      <rect x="17.5" y="4" width="5" height="38" style={{ fill: 'var(--accent)' }} />
      <rect x="28" y="8" width="5" height="26" style={{ fill: 'var(--accent)' }} />
      <rect x="3" y="15" width="34" height="11" fill="#12161c" />
      <text x="20" y="23.8" textAnchor="middle" fontFamily="Barlow Condensed, sans-serif" fontWeight={800}
        fontSize={label.length > 3 ? 8 : 10} fill="#fff">{label}</text>
      <path d={AUTO_SHIELD} fill="none" strokeWidth={1.5} stroke="#12161c" />
    </svg>
  )
}

function Shape({ shape }: { shape: CrestConfig['shape'] }) {
  if (shape === 'circle') return <circle cx="50" cy="55" r="45" />
  if (shape === 'rounded') return <rect x="6" y="7" width="88" height="96" rx="18" />
  return <path d={SHIELD} />
}

/** 업로드 이미지는 필터 없이 원래 색상으로 표시한다. 로드 실패 시 기본 방패로 돌아간다. */
export function Crest({ name, size = 44, appearance }: { name: string; size?: number; appearance?: ClubAppearance | null }) {
  const clipId = `crest-${useId().replace(/:/g, '')}`
  const [failedImage, setFailedImage] = useState<string | null>(null)
  const config = appearance?.crest
  const url = appearance?.imageUrl
  if (config?.mode === 'image' && url && failedImage !== url) {
    return <img src={url} width={size} height={(size * 46) / 40} alt={`${name} 엠블럼`}
      onError={() => setFailedImage(url)} style={{ flex: 'none', objectFit: 'contain', filter: 'none' }} />
  }
  if (!config || config.mode !== 'design') return <AutoCrest name={name} size={size} />

  const label = config.text
  return (
    <svg width={size} height={(size * 46) / 40} viewBox="0 0 100 115" role="img" aria-label={`${name} 엠블럼`} style={{ flex: 'none' }}>
      <defs><clipPath id={clipId}><Shape shape={config.shape} /></clipPath></defs>
      <g clipPath={`url(#${clipId})`}>
        <rect width="100" height="115" fill={config.primaryColor} />
        {config.pattern === 'stripes' ? (
          <g fill={config.secondaryColor}>
            {[0, 20, 40, 60, 80, 100].map((x) => <rect key={x} x={x} width="10" height="115" />)}
          </g>
        ) : config.pattern === 'diagonal' ? (
          <path d="M-10 82 L92 -20 L120 8 L18 110 Z" fill={config.secondaryColor} />
        ) : null}
        {config.symbol === 'ball' ? (
          <g stroke={config.textColor} strokeWidth="2.2" fill="none">
            <circle cx="50" cy="37" r="13" />
            <path d="M50 31 L56 35 L54 42 H46 L44 35 Z M50 31 V24 M56 35 L62 32 M54 42 L58 47 M46 42 L42 47 M44 35 L38 32" />
          </g>
        ) : config.symbol === 'star' ? (
          <path d="M50 22 L54 31 L64 32 L57 39 L59 49 L50 44 L41 49 L43 39 L36 32 L46 31 Z" fill={config.textColor} />
        ) : null}
        {label ? (
          <>
            <rect x="6" y={config.symbol === 'none' ? 41 : 56} width="88" height="28" fill={config.primaryColor} opacity="0.94" />
            <text x="50" y={config.symbol === 'none' ? 61 : 76} textAnchor="middle" fill={config.textColor}
              fontFamily="Barlow Condensed, Noto Sans KR, sans-serif" fontWeight="800"
              fontSize={[...label].length > 4 ? 12 : [...label].length > 3 ? 15 : 22}>{label}</text>
          </>
        ) : null}
      </g>
      <g fill="none" stroke={config.secondaryColor} strokeWidth="3"><Shape shape={config.shape} /></g>
    </svg>
  )
}
