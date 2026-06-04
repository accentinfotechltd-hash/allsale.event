import { Component } from "react";

/**
 * Top-level error boundary. Catches any render-time exception in the React tree
 * and shows a friendly fallback instead of a blank white page. Logs the error
 * to the console so it can still be debugged via DevTools.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, stack: "" };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error, info?.componentStack);
    this.setState({ stack: info?.componentStack || "" });
  }

  reset = () => {
    this.setState({ hasError: false, error: null, stack: "" });
  };

  copyReport = async () => {
    const route = typeof window !== "undefined" ? window.location.pathname + window.location.search : "";
    const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
    const body = [
      `Route: ${route}`,
      `When:  ${new Date().toISOString()}`,
      `Agent: ${ua}`,
      ``,
      `Error: ${this.state.error?.message || String(this.state.error)}`,
      ``,
      `Stack:`,
      String(this.state.error?.stack || ""),
      ``,
      `Component stack:`,
      String(this.state.stack || ""),
    ].join("\n");
    try {
      await navigator.clipboard.writeText(body);
      // Best-effort UI feedback — we can't import toast in a class component
      // without coupling, so a simple alert keeps the bundle small and the
      // signal clear.
      // eslint-disable-next-line no-alert
      alert("Crash report copied to clipboard. Paste it back to support so we can pinpoint the bug.");
    } catch {
      // Fall through — at least the textarea below is selectable.
    }
  };

  render() {
    if (!this.state.hasError) return this.props.children;
    const route = typeof window !== "undefined" ? window.location.pathname : "";
    return (
      <div className="min-h-screen flex items-center justify-center p-6" style={{ background: "var(--bg)", color: "var(--text)" }}>
        <div className="max-w-md text-center">
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Something went wrong</div>
          <h1 className="serif text-4xl mb-3">We hit a snag.</h1>
          <p className="text-sm mb-2" style={{ color: "var(--text-muted)" }}>
            The page failed to render. Reloading usually fixes it.
          </p>
          {route && (
            <p className="text-xs mb-6 font-mono" style={{ color: "var(--text-dim)" }}>
              {route}
            </p>
          )}
          <div className="flex gap-3 justify-center flex-wrap">
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
            <button
              type="button"
              className="btn-ghost"
              onClick={this.copyReport}
              data-testid="error-copy-btn"
            >
              Copy crash report
            </button>
          </div>
          {this.state.error?.message && (
            <pre className="mt-6 text-xs text-left p-3 rounded-lg overflow-auto max-h-64" style={{ background: "var(--bg-card)", color: "var(--text-dim)" }}>
              {String(this.state.error.message)}
              {this.state.stack ? `\n\nComponent stack:${this.state.stack}` : ""}
            </pre>
          )}
        </div>
      </div>
    );
  }
}
