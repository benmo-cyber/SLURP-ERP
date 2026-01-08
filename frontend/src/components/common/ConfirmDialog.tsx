import './ConfirmDialog.css'

interface ConfirmDialogProps {
  message: string
  onConfirm: () => void
  onCancel: () => void
}

function ConfirmDialog({ message, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content confirm-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="confirm-message">{message}</div>
        <div className="confirm-actions">
          <button onClick={onCancel} className="btn btn-secondary">
            No
          </button>
          <button onClick={onConfirm} className="btn btn-primary">
            Yes
          </button>
        </div>
      </div>
    </div>
  )
}

export default ConfirmDialog






