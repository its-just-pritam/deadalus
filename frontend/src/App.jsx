import { useState } from 'react'
import { ArrowUp, Bot, Check, CircleHelp, Clock3, Copy, RefreshCw, RotateCcw, Send, Sparkles, UserRound } from 'lucide-react'

const suggestions = [
  'Who is on reserve at BLR on 2026-09-15?',
  'What is C-1042\'s duty-hour headroom?',
  'Which flights are affected by the BLR closure on 17 Sep?',
]

const initialMessages = [
  {
    id: 1,
    role: 'assistant',
    content: 'Crew Operations is ready. Ask about reserves, schedules, duty limits, pairings, or recovery options.',
    createdAt: new Date().toISOString(),
  },
]

function formatTimestamp(value) {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatResponseTime(value) {
  if (value === undefined) return 'Ready'
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`
}

function formatError(error) {
  const detail = error?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return 'The operations service could not answer right now.'
}

export function App() {
  const [messages, setMessages] = useState(initialMessages)
  const [question, setQuestion] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState('')
  const [copiedId, setCopiedId] = useState(null)

  async function sendQuestion(event, questionOverride = '') {
    event?.preventDefault()
    const trimmed = (questionOverride || question).trim()
    if (!trimmed || isSending) return

    const userMessage = { id: Date.now(), role: 'user', content: trimmed }
    setMessages((current) => [...current, userMessage])
    setQuestion('')
    setError('')
    setIsSending(true)
    const requestStartedAt = performance.now()

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed }),
      })
      const payload = await response.json()
      if (!response.ok) throw payload
      const responseTimeMs = Math.round(performance.now() - requestStartedAt)
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: payload.answer,
          createdAt: new Date().toISOString(),
          responseTimeMs,
          sourceQuestion: trimmed,
        },
      ])
    } catch (requestError) {
      const message = formatError(requestError)
      const responseTimeMs = Math.round(performance.now() - requestStartedAt)
      setError(message)
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: `I could not complete that request. ${message}`,
          createdAt: new Date().toISOString(),
          responseTimeMs,
          sourceQuestion: trimmed,
        },
      ])
    } finally {
      setIsSending(false)
    }
  }

  function resetConversation() {
    setMessages(initialMessages)
    setError('')
    setQuestion('')
  }

  async function copyResponse(message) {
    await navigator.clipboard.writeText(message.content)
    setCopiedId(message.id)
    window.setTimeout(() => setCopiedId(null), 1500)
  }

  function retryResponse(message) {
    setQuestion(message.sourceQuestion)
    sendQuestion(undefined, message.sourceQuestion)
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <img className="brand-logo" src="/dcotex-logo.webp" alt="dCortex" />
          <div>
            <p className="eyebrow">dCortex Air</p>
            <h1>Control room</h1>
          </div>
        </div>
        <div className="sidebar-rule" />
        <div className="status-card">
          <span className="status-dot" />
          <div>
            <strong>Operations API online</strong>
            <span>Verified retrieval enabled</span>
          </div>
        </div>
        <nav className="side-nav" aria-label="Workspace sections">
          <span className="nav-item active"><Sparkles size={16} /> Operations assistant</span>
          <span className="nav-item"><Clock3 size={16} /> Live snapshot <small>14 Sep</small></span>
        </nav>
        <div className="sidebar-footer">
          <p>All times UTC</p>
          <p>Read-only operational data</p>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Crew control / assistant</p>
            <h2>Ask the operations desk</h2>
          </div>
          <button className="icon-button" onClick={resetConversation} title="Reset conversation" aria-label="Reset conversation">
            <RotateCcw size={17} />
          </button>
        </header>

        <div className="content-grid">
          <section className="chat-panel">
            <div className="conversation" aria-live="polite">
              {messages.map((message) => (
                <article className={`message-row ${message.role}`} key={message.id}>
                  <div className="avatar" aria-hidden="true">
                    {message.role === 'assistant' ? <Bot size={17} /> : <UserRound size={17} />}
                  </div>
                  <div className="message-bubble">
                    <span className="message-label">{message.role === 'assistant' ? 'Operations desk' : 'You'}</span>
                    <p>{message.content}</p>
                    {message.role === 'assistant' && message.sourceQuestion && (
                      <div className="response-meta">
                        <span>{formatTimestamp(message.createdAt)}</span>
                        <span>{formatResponseTime(message.responseTimeMs)}</span>
                        <button className="response-action" onClick={() => copyResponse(message)} title="Copy response" aria-label="Copy response">
                          {copiedId === message.id ? <Check size={13} /> : <Copy size={13} />}
                        </button>
                        {message.sourceQuestion && (
                          <button className="response-action" onClick={() => retryResponse(message)} disabled={isSending} title="Retry response" aria-label="Retry response">
                            <RefreshCw size={13} />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </article>
              ))}
              {isSending && (
                <article className="message-row assistant">
                  <div className="avatar"><Bot size={17} /></div>
                  <div className="message-bubble typing"><span /><span /><span /></div>
                </article>
              )}
            </div>

            {messages.length === 1 && (
              <aside className="briefing-panel">
                <div className="briefing-heading">
                  <div>
                    <p className="eyebrow">Quick start</p>
                    <h3>Useful desk queries</h3>
                  </div>
                  <ArrowUp size={17} />
                </div>
                <div className="suggestion-list">
                  {suggestions.map((suggestion) => (
                    <button key={suggestion} className="suggestion" onClick={() => setQuestion(suggestion)}>
                      <span>{suggestion}</span><ArrowUp size={15} />
                    </button>
                  ))}
                </div>
                <div className="briefing-note">
                  <span className="note-icon"><Bot size={16} /></span>
                  <p>The assistant retrieves facts first, then explains the operational result.</p>
                </div>
              </aside>
            )}

            <div className="composer-wrap">
              {error && <div className="error-strip"><CircleHelp size={16} /> {error}</div>}
              <form className="composer" onSubmit={sendQuestion}>
                <textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      sendQuestion(event)
                    }
                  }}
                  placeholder="Ask about the current operation..."
                  rows="2"
                  aria-label="Question"
                />
                <button className="send-button" type="submit" disabled={!question.trim() || isSending} title="Send question" aria-label="Send question">
                  {isSending ? <span className="spinner" /> : <Send size={18} />}
                </button>
              </form>
              <p className="composer-note">Answers are grounded in the operational API and its verified tools.</p>
            </div>
          </section>
        </div>
      </section>
    </main>
  )
}
