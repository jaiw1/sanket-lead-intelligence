import { Component } from 'react'
import ErrorState from './states/ErrorState'

/**
 * Last line of defence: a render-time crash shows a readable panel with the request id
 * (when the failure came from the API) instead of a blank white page. 5xx responses are
 * thrown as ApiError by lib/api.js and land here when a screen does not catch them.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
    this.reset = this.reset.bind(this)
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // No telemetry endpoint in this build; the console is what a developer has on the box.
    if (import.meta.env?.DEV) console.error('Unhandled UI error', error, info)
  }

  reset() {
    this.setState({ error: null })
    if (this.props.onReset) this.props.onReset()
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    if (this.props.fallback) return this.props.fallback(error, this.reset)
    return (
      <div className="p-6">
        <ErrorState
          title={this.props.title || 'This screen could not be displayed'}
          error={error}
          message={
            error?.isServer
              ? 'The server reported an error. Nothing you were doing has been saved.'
              : 'An unexpected error occurred while rendering this screen.'
          }
          onRetry={this.reset}
          retryLabel="Reload this screen"
        />
      </div>
    )
  }
}
