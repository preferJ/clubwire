import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { ThemeProvider } from './lib/theme'
import { UserAuthProvider } from './lib/userAuth'
import './styles/global.css'
import './styles/themes.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider><UserAuthProvider><App /></UserAuthProvider></ThemeProvider>
  </StrictMode>,
)
