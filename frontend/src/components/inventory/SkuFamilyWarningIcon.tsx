import './SkuFamilyWarningIcon.css'

export interface SkuFamilyWarning {
  code: string
  message: string
  hint?: string
}

export function SkuFamilyWarningIcon({ warnings }: { warnings?: SkuFamilyWarning[] }) {
  if (!warnings?.length) return null
  const lines = warnings.map((w) => {
    const fix = (w.hint || '').trim()
    return fix ? `${w.message}\n\nHow to fix: ${fix}` : w.message
  })
  const label = lines.join('\n\n—\n\n')
  return (
    <span className="sku-family-warning-wrap" tabIndex={0}>
      <span className="sku-family-warning-icon" role="img" aria-label={label}>
        !
      </span>
      <span className="sku-family-warning-tooltip" role="tooltip">
        {warnings.map((w, i) => (
          <span key={w.code + i} className="sku-family-warning-tooltip-block">
            <span className="sku-family-warning-tooltip-title">{w.message}</span>
            {w.hint ? (
              <span className="sku-family-warning-tooltip-hint">How to fix: {w.hint}</span>
            ) : null}
          </span>
        ))}
      </span>
    </span>
  )
}
