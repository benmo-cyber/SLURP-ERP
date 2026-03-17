import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { passwordResetConfirm } from '../api/auth'
import './Login.css'

export default function ResetPassword() {
  const [searchParams] = useSearchParams()
  const uid = searchParams.get('uid') || ''
  const token = searchParams.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    if (!uid || !token) {
      setError('Invalid reset link')
      return
    }
    setSubmitting(true)
    try {
      const res = await passwordResetConfirm(uid, token, password)
      if (res.error) {
        setError(res.error)
      } else {
        setDone(true)
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Update failed. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="login-brand">
            <h1>Password updated</h1>
            <p className="login-subtitle">You can sign in with your new password.</p>
          </div>
          <p className="login-forgot">
            <Link to="/login">Sign in</Link>
          </p>
        </div>
      </div>
    )
  }

  if (!uid || !token) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="login-brand">
            <h1>Invalid link</h1>
            <p className="login-subtitle">This reset link is missing or invalid.</p>
          </div>
          <p className="login-forgot">
            <Link to="/forgot-password">Request a new link</Link>
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <h1>Set new password</h1>
          <p className="login-subtitle">Enter your new password below.</p>
        </div>
        <form onSubmit={handleSubmit} className="login-form">
          {error && <div className="login-error">{error}</div>}
          <div className="form-group">
            <label htmlFor="password">New password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <label htmlFor="confirm">Confirm password</label>
            <input
              id="confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
            />
          </div>
          <button type="submit" className="login-submit" disabled={submitting}>
            {submitting ? 'Updating…' : 'Update password'}
          </button>
          <p className="login-forgot">
            <Link to="/login">Back to sign in</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
