import { Component } from "react";

/**
 * Top-level error boundary. Catches any render-time exception in the React tree
 * and shows a friendly fallback instead of a blank white page. Logs the error
 * to the console so it can still be debugged via DevTools.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error, info?.componentStack);
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="min-h-screen flex items-center justify-center p-6" style={{ background: "var(--bg)", color: "var(--text)" }}>
        <div className="max-w-md text-center">
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Something went wrong</div>
          <h1 className="serif text-4xl mb-3">We hit a snag.</h1>
          <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
            The page failed to render. Reloading usually fixes it.
          </p>
          <div className="flex gap-3 justify-center">
            <button
              type="button"
              className="btn-primary"
              onClick={() => window.location.reload()}
              data-testid="error-reload-btn"
            >
              Reload
            </button>
            <a href="/" className="btn-ghost" data-testid="error-home-btn">
              Go home
            </a>
          </div>
          {this.state.error?.message && (
            <pre className="mt-6 text-xs text-left p-3 rounded-lg overflow-auto" style={{ background: "var(--bg-card)", color: "var(--text-dim)" }}>
              {String(this.state.error.message)}
            </pre>
          )}
        </div>
      </div>
    );
  }
}
