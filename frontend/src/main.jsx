import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { checkForDesktopUpdatesOnStartup } from './updater/checkForUpdates'

checkForDesktopUpdatesOnStartup()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
