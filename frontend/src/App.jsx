import { useEffect, useState } from 'react'
import { ArrowUp, Bot, Check, CircleHelp, Clock3, Copy, RefreshCw, RotateCcw, Send, Sparkles, UserRound } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const suggestions = [
  'Who is on reserve at BLR on 2026-09-15?',
  'What is C-1042\'s duty-hour headroom?',
  'Which flights are affected by the BLR closure on 17 Sep?',
]
const SESSION_ID = 'default'

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

  useEffect(() => {
    let active = true
    fetch(`/api/chat/history?session_id=${SESSION_ID}`)
      .then((response) => (response.ok ? response.json() : []))
      .then(async (history) => {
        if (!active || history.length === 0) return
        const mapped = history.map((message) => ({
          id: message.message_id,
          role: message.role,
          content: message.content,
          createdAt: message.created_at,
          responseTimeMs: message.response_time_ms,
          sourceQuestion: message.source_question,
        }))
        // Tool calls are logged against the user question's message_id, not the assistant reply's.
        const withToolCalls = await Promise.all(
          mapped.map(async (message, index) => {
            if (message.role !== 'assistant') return message
            const questionMessage = mapped[index - 1]
            if (!questionMessage || questionMessage.role !== 'user') return message
            try {
              const response = await fetch(`/api/chat/tool-calls?message_id=${questionMessage.id}`)
              if (!response.ok) return message
              return { ...message, toolCalls: await response.json() }
            } catch {
              return message
            }
          })
        )
        if (active) setMessages(withToolCalls)
      })
      .catch(() => {})

    return () => {
      active = false
    }
  }, [])

  async function sendQuestion(event, questionOverride = '') {
    event?.preventDefault()
    const trimmed = (questionOverride || question).trim()
    if (!trimmed || isSending) return

    const userMessage = { id: `user-${Date.now()}`, role: 'user', content: trimmed }
    setMessages((current) => [...current, userMessage])
    setQuestion('')
    setError('')
    setIsSending(true)
    const requestStartedAt = performance.now()

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed, session_id: SESSION_ID }),
      })
      const payload = await response.json()
      if (!response.ok) throw payload
      setMessages((current) => [
        ...current,
        {
          id: payload.message_id,
          role: 'assistant',
          content: '',
          createdAt: payload.created_at,
          sourceQuestion: trimmed,
          pending: true,
          toolCalls: [],
        },
      ])
      pollForAnswer(payload.message_id, requestStartedAt)
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
      setIsSending(false)
    }
  }

  function finishWithError(messageId, message, requestStartedAt) {
    const responseTimeMs = Math.round(performance.now() - requestStartedAt)
    setError(message)
    setMessages((current) => current.map((entry) => (
      entry.id === messageId
        ? { ...entry, content: `I could not complete that request. ${message}`, responseTimeMs, pending: false }
        : entry
    )))
    setIsSending(false)
  }

  async function pollForAnswer(messageId, requestStartedAt) {
    try {
      const toolCallsResponse = await fetch(`/api/chat/tool-calls?message_id=${messageId}`)
      if (toolCallsResponse.ok) {
        const toolCalls = await toolCallsResponse.json()
        setMessages((current) => current.map((entry) => (
          entry.id === messageId ? { ...entry, toolCalls } : entry
        )))
      }

      const statusResponse = await fetch(`/api/chat/status?message_id=${messageId}`)
      const status = await statusResponse.json()
      if (!statusResponse.ok) throw status

      if (status.status === 'pending') {
        window.setTimeout(() => pollForAnswer(messageId, requestStartedAt), 800)
        return
      }

      if (status.status === 'done') {
        setMessages((current) => current.map((entry) => (
          entry.id === messageId
            ? {
                ...entry,
                content: status.answer,
                createdAt: status.created_at,
                responseTimeMs: status.response_time_ms,
                pending: false,
              }
            : entry
        )))
        setIsSending(false)
        return
      }

      finishWithError(messageId, status.error || 'The operations service could not answer right now.', requestStartedAt)
    } catch (pollError) {
      finishWithError(messageId, formatError(pollError), requestStartedAt)
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
                  <div className="message-column">
                    {(message.pending || (message.toolCalls && message.toolCalls.length > 0)) && (
                      <div className="tool-call-panel">
                        <span className="tool-call-panel-label">Retrieval tools</span>
                        {message.toolCalls && message.toolCalls.length > 0 ? (
                          <ul className="tool-call-list">
                            {message.toolCalls.map((call) => (
                              <li className={`tool-call-item ${call.success ? 'ok' : 'failed'}`} key={call.id}>
                                <span className="tool-call-name">{call.tool_name}</span>
                                <span className="tool-call-meta">
                                  {call.method} {call.status_code ?? ''} · {call.duration_ms ? `${Math.round(call.duration_ms)} ms` : '...'}
                                </span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="tool-call-empty">Selecting a retrieval tool...</p>
                        )}
                      </div>
                    )}
                    <div className="message-bubble">
                      <span className="message-label">{message.role === 'assistant' ? 'Operations desk' : 'You'}</span>
                      {message.pending ? (
                        <div className="typing"><span /><span /><span /></div>
                      ) : message.role === 'assistant' ? (
                        <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div>
                      ) : (
                        <p>{message.content}</p>
                      )}
                      {message.role === 'assistant' && !message.pending && message.sourceQuestion && (
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
                  </div>
                </article>
              ))}
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
