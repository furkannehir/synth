import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import ForcedUpdateGate from './updater/ForcedUpdateGate'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ForcedUpdateGate>
      <App />
    </ForcedUpdateGate>
  </StrictMode>,
)
