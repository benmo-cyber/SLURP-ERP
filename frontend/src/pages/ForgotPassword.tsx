import { useState } from 'react'
import { Link } from 'react-router-dom'
import { passwordResetRequest } from '../api/auth'
import './Login.css'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const res = await passwordResetRequest(email.trim())
      if (res.error) {
        setError(res.error)
      } else {
        setSent(true)
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Request failed. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (sent) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="login-brand">
            <h1>Check your email</h1>
            <p className="login-subtitle">
              If that address is on file, we sent instructions to reset your password.
            </p>
          </div>
          <p className="login-forgot">
            <Link to="/login">Back to sign in</Link>
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <h1>Forgot password</h1>
          <p className="login-subtitle">Enter your email and we’ll send a reset link.</p>
        </div>
        <form onSubmit={handleSubmit} className="login-form">
          {error && <div className="login-error">{error}</div>}
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              autoFocus
            />
          </div>
          <button type="submit" className="login-submit" disabled={submitting}>
            {submitting ? 'Sending…' : 'Send reset link'}
          </button>
          <p className="login-forgot">
            <Link to="/login">Back to sign in</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
