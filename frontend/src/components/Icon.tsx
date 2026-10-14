// 선 아이콘(시안과 동일한 stroke 스타일). 장식용이므로 aria-hidden.

const PATHS: Record<string, string[]> = {
  lock: ['M5 11h14v10H5z', 'M8 11V8a4 4 0 0 1 8 0v3'],
  back: ['M15 5l-7 7 7 7'],
  chevron: ['M9 5l7 7-7 7'],
  wire: ['M4 5h13v14H6a2 2 0 0 1-2-2z', 'M17 9h3v8a2 2 0 0 1-2 2', 'M7 9h7M7 13h7M7 16h4'],
  calendar: ['M4 5h16v15H4z', 'M4 10h16M9 3v4M15 3v4'],
  trophy: ['M8 4h8v5a4 4 0 0 1-8 0z', 'M8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4', 'M12 13v4M9 20h6'],
  users: ['M9 5a3 3 0 1 1 0 6 3 3 0 0 1 0-6z', 'M3 19a6 6 0 0 1 12 0', 'M17 6.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5z', 'M15.5 14.2A5 5 0 0 1 21 19'],
  share: ['M12 4v11M8 8l4-4 4 4', 'M5 13v6h14v-6'],
  pause: ['M9 5v14M15 5v14'],
  play: ['M8 5l11 7-11 7z'],
  stop: ['M6 6h12v12H6z'],
  plus: ['M12 5v14M5 12h14'],
  check: ['M5 12.5l4.5 4.5L19 7.5'],
  shuffle: ['M4 7h3c4 0 6 10 10 10h3M4 17h3c1.5 0 2.7-1.4 3.7-3M14 9.5C15 8 16 7 17 7h3', 'M18 4l3 3-3 3M18 14l3 3-3 3'],
  scale: ['M12 4v16M7 20h10M5 7h14', 'M5 7l-3 6a3 3 0 0 0 6 0zM19 7l-3 6a3 3 0 0 0 6 0z'],
  warn: ['M12 4l9 16H3z', 'M12 10v4M12 17v.5'],
  info: ['M12 4a8 8 0 1 1 0 16 8 8 0 0 1 0-16z', 'M12 11v5M12 8v.5'],
  refresh: ['M20 12a8 8 0 1 1-2.3-5.7', 'M20 4v5h-5'],
  del: ['M9 6h11v12H9l-6-6z', 'M12 10l4 4M16 10l-4 4'],
  search: ['M11 5a6 6 0 1 1 0 12 6 6 0 0 1 0-12z', 'M20 20l-4.5-4.5'],
  settings: ['M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z', 'M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z'],
  close: ['M6 6l12 12M18 6L6 18'],
  menu: ['M4 7h16M4 12h16M4 17h16'],
}

export function Icon({ name, size = 20, stroke = 1.8 }: { name: keyof typeof PATHS | string; size?: number; stroke?: number }) {
  const paths = PATHS[name] ?? []
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  )
}
