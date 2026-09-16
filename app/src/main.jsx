import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import AuthProvider from './auth/AuthContext'
import ErrorBoundary from './components/ErrorBoundary'
import { routerBasename } from './lib/basepath'
import './index.css'

// The boundary is OUTSIDE the router deliberately: a crash inside a route should still
// render a readable panel, and a crash in the router itself would otherwise be a white page.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <BrowserRouter
        basename={routerBasename()}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>,
)
