export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="notice notice--error" role="alert">
      <div>{message}</div>
      {onRetry && (
        <button
          type="button"
          className="button button--ghost"
          style={{ marginTop: 10 }}
          onClick={onRetry}
        >
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyNotice({ children }: { children: React.ReactNode }) {
  return <div className="notice notice--empty">{children}</div>
}

export function LoadingPanel({ label }: { label: string }) {
  return (
    <div className="panel" aria-busy="true">
      <div className="panel__body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--ink-muted)' }}>
          <span className="spinner" aria-hidden="true" />
          <span role="status">{label}</span>
        </div>
        <div className="skeleton" style={{ height: 14, width: '70%' }} />
        <div className="skeleton" style={{ height: 14, width: '45%' }} />
        <div className="skeleton" style={{ height: 180 }} />
      </div>
    </div>
  )
}
