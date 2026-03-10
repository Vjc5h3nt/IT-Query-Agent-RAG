import { useEffect, useRef, useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import './MessageList.css';

const WELCOME_PROMPTS = [
    {
        heading: "What's on your mind?",
        sub: "Ask me anything about your documents, data, or knowledge base.",
    },
    {
        heading: "Ready when you are.",
        sub: "Bring your toughest questions — I'll dig through your knowledge base to find answers.",
    },
    {
        heading: "Let's get to work.",
        sub: "Ask about your documents, tickets, policies, or anything in the knowledge base.",
    },
    {
        heading: "How can I assist you today?",
        sub: "I can search your documents, summarise content, or answer technical questions.",
    },
    {
        heading: "Your knowledge base is ready.",
        sub: "What would you like to explore, clarify, or investigate?",
    },
    {
        heading: "Ask me anything.",
        sub: "From technical queries to document search — I'm here to help you find answers fast.",
    },
    {
        heading: "Good to see you.",
        sub: "What problem can I help you solve today?",
    },
    {
        heading: "Intelligence at your fingertips.",
        sub: "Start with a question and I'll surface the most relevant information for you.",
    },
];

function MessageList({ messages, onRegenerate, loading, userName, sessionId }) {
    const messagesEndRef = useRef(null);
    const [copiedIndex, setCopiedIndex] = useState(null);

    const welcomePrompt = useMemo(
        () => WELCOME_PROMPTS[Math.floor(Math.random() * WELCOME_PROMPTS.length)],
        // Re-pick whenever the session changes
        [sessionId]
    );
    const [showAuditIndex, setShowAuditIndex] = useState(null);
    const [showMetricsIndex, setShowMetricsIndex] = useState(null);
    const [expandedSources, setExpandedSources] = useState({});

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, loading]);

    const formatTime = (timestamp) => {
        if (!timestamp) return '';
        const date = new Date(timestamp);
        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    };

    const handleCopy = (content, index) => {
        navigator.clipboard.writeText(content).then(() => {
            setCopiedIndex(index);
            setTimeout(() => setCopiedIndex(null), 2000);
        });
    };

    const toggleSources = (index) => {
        setExpandedSources(prev => ({ ...prev, [index]: !prev[index] }));
    };

    return (
        <div className="message-list">
            {messages.length === 0 && !loading ? (
                <div className="empty-state">
                    <h3>{welcomePrompt.heading}</h3>
                    <p>{welcomePrompt.sub}</p>
                </div>
            ) : (
                <div className="messages-container">
                    {messages.map((msg, index) => (
                        <div key={index} className={`message-wrapper ${msg.role}`}>
                            {/* Message header — author only, no Audit here */}
                            <div className="message-header">
                                <div className="author-info">
                                    <div className="avatar">
                                        {msg.role === 'user' ? (
                                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                                        ) : (
                                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z"></path><path d="M12 6v6l4 2"></path></svg>
                                        )}
                                    </div>
                                    <div className="author-meta">
                                        <span className="author-name">
                                            {msg.role === 'user' ? userName : 'Agent'}
                                        </span>
                                        {msg.role === 'assistant' && <span className="plus-badge">AI</span>}
                                        <span className="message-time">{formatTime(msg.timestamp)}</span>
                                    </div>
                                </div>
                            </div>

                            {/* Message body */}
                            <div className="message-body">
                                <div className="message-text">
                                    <ReactMarkdown
                                        components={{
                                            a: ({ node, ...props }) => {
                                                if (props.href?.startsWith('#cite-')) {
                                                    const id = props.href.split('-')[1];
                                                    return (
                                                        <span
                                                            className="citation-badge"
                                                            title="Scroll to source"
                                                            onClick={(e) => {
                                                                e.preventDefault();
                                                                const el = document.getElementById(`source-card-${id}`);
                                                                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                                            }}
                                                        >
                                                            S{id}
                                                        </span>
                                                    );
                                                }
                                                return <a {...props} target="_blank" rel="noopener noreferrer" />;
                                            }
                                        }}
                                    >
                                        {msg.content.replace(/\[S(\d+)\]/g, '[$1](#cite-$1)')}
                                    </ReactMarkdown>
                                </div>

                                {/* ── Unified meta-row ── */}
                                {msg.role === 'assistant' && (
                                    (msg.citations?.length > 0 || msg.rerank_summary || msg.metrics)
                                ) && (
                                        <div className="msg-meta-row">

                                            {/* 1. Sources chip */}
                                            {msg.citations && msg.citations.length > 0 && (
                                                <button
                                                    className={`sources-toggle-chip ${expandedSources[index] ? 'open' : ''}`}
                                                    onClick={() => toggleSources(index)}
                                                    title={expandedSources[index] ? 'Hide sources' : 'Show sources'}
                                                >
                                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                                                    Sources ({msg.citations.length})
                                                    <svg className="chevron" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                                                </button>
                                            )}

                                            {/* 2. Metrics chip */}
                                            {msg.metrics && (
                                                <button
                                                    className={`metrics-chip ${showMetricsIndex === index ? 'active' : ''}`}
                                                    onClick={() => setShowMetricsIndex(showMetricsIndex === index ? null : index)}
                                                    title="Response metrics"
                                                >
                                                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                                                    {msg.metrics.latency_s}s
                                                </button>
                                            )}

                                            {/* 3. Reranking Log chip */}
                                            {msg.rerank_summary && (
                                                <button
                                                    className="audit-chip"
                                                    onClick={() => setShowAuditIndex(index)}
                                                    title="View reranking log"
                                                >
                                                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
                                                    Reranking
                                                </button>
                                            )}


                                        </div>
                                    )}

                                {/* Metrics inline popup */}
                                {showMetricsIndex === index && msg.metrics && (
                                    <div className="metrics-popup">
                                        <div className="metrics-popup-header">
                                            <span>Response Metrics</span>
                                            <button className="metrics-close" onClick={() => setShowMetricsIndex(null)}>×</button>
                                        </div>
                                        <div className="metrics-grid">
                                            <div className="metrics-item">
                                                <span className="metrics-label">Total time</span>
                                                <span className="metrics-value">{msg.metrics.latency_s}s</span>
                                            </div>
                                            <div className="metrics-item">
                                                <span className="metrics-label">Retrieval</span>
                                                <span className="metrics-value">{msg.metrics.retrieval_s ?? 0}s</span>
                                            </div>
                                            <div className="metrics-item">
                                                <span className="metrics-label">Generation</span>
                                                <span className="metrics-value">{msg.metrics.generation_s ?? 0}s</span>
                                            </div>
                                            <div className="metrics-item">
                                                <span className="metrics-label">Input tokens</span>
                                                <span className="metrics-value">{msg.metrics.input_tokens ?? '—'}</span>
                                            </div>
                                            <div className="metrics-item">
                                                <span className="metrics-label">Output tokens</span>
                                                <span className="metrics-value">{msg.metrics.output_tokens ?? '—'}</span>
                                            </div>
                                            <div className="metrics-item">
                                                <span className="metrics-label">Total tokens</span>
                                                <span className="metrics-value highlight">{msg.metrics.total_tokens ?? '—'}</span>
                                            </div>
                                            <div className="metrics-item full-width">
                                                <span className="metrics-label">Query type</span>
                                                <span className={`metrics-badge ${msg.metrics.query_type === 'rag' ? 'badge-rag' : 'badge-casual'}`}>
                                                    {msg.metrics.query_type === 'rag' ? 'RAG' : 'Casual'}
                                                </span>
                                            </div>
                                            {msg.metrics.sources_retrieved > 0 && (
                                                <div className="metrics-item full-width">
                                                    <span className="metrics-label">Chunks retrieved</span>
                                                    <span className="metrics-value">{msg.metrics.sources_retrieved}</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}

                                {/* Expanded sources list */}
                                {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && expandedSources[index] && (
                                    <div className="sources-expanded">
                                        {msg.citations.map((cite, i) => (
                                            <div key={i} id={`source-card-${cite.metadata?.source_index || i + 1}`} className="source-tag">
                                                <span className="source-index">S{cite.metadata?.source_index || i + 1}</span>
                                                <span className="source-label">{cite.label}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}


                                {/* Message footer actions */}
                                {msg.role === 'assistant' && (
                                    <div className="message-footer">
                                        <div className="interaction-actions">
                                            <button className="icon-btn" title="Helpful">
                                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path></svg>
                                            </button>
                                            <button className="icon-btn" title="Not helpful">
                                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"></path></svg>
                                            </button>
                                            <button
                                                className={`icon-btn copy-btn ${copiedIndex === index ? 'copied' : ''}`}
                                                onClick={() => handleCopy(msg.content, index)}
                                                title={copiedIndex === index ? 'Copied!' : 'Copy message'}
                                            >
                                                {copiedIndex === index ? (
                                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                                                ) : (
                                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                                )}
                                            </button>
                                        </div>
                                        <button className="btn-regenerate" onClick={() => onRegenerate(index)} title="Regenerate response">
                                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M23 4v6h-6"></path><path d="M1 20v-6h6"></path><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
                                            Regenerate
                                        </button>
                                    </div>
                                )}{/* end message-footer */}
                            </div>{/* end message-body */}

                            {/* Audit overlay modal */}
                            {showAuditIndex === index && msg.rerank_summary && (
                                <div className="rerank-audit-overlay" onClick={() => setShowAuditIndex(null)}>
                                    <div className="rerank-audit-panel" onClick={e => e.stopPropagation()}>
                                        <div className="audit-panel-header">
                                            <h4>
                                                <span className="icon">🧙‍♂️</span>
                                                Cross-Encoder Retrieval Audit
                                            </h4>
                                            <button className="close-audit" onClick={() => setShowAuditIndex(null)}>&times;</button>
                                        </div>
                                        <div className="audit-info-text">
                                            The Cross-Encoder analyzed candidates and re-ordered them based on deep semantic relevance to your query.
                                        </div>
                                        <div className="audit-table-wrapper">
                                            <table className="audit-table">
                                                <thead>
                                                    <tr>
                                                        <th>Final Rank</th>
                                                        <th>Document</th>
                                                        <th>Initial Rank</th>
                                                        <th>Impact</th>
                                                        <th>Score</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {msg.rerank_summary.map((res, i) => {
                                                        const jump = res.initial_rank - res.final_rank;
                                                        const isUp = jump > 0;
                                                        const isDown = jump < 0;
                                                        return (
                                                            <tr key={i}>
                                                                <td className="final-rank-cell">#{res.final_rank}</td>
                                                                <td className="doc-cell">
                                                                    <div className="doc-name">{res.filename}</div>
                                                                    <div className="doc-page">Page {res.page}</div>
                                                                </td>
                                                                <td className="initial-rank-cell">#{res.initial_rank}</td>
                                                                <td className={`impact-cell ${isUp ? 'positive' : isDown ? 'negative' : ''}`}>
                                                                    {isUp ? `↑${jump}` : isDown ? `↓${Math.abs(jump)}` : '-'}
                                                                </td>
                                                                <td className="score-cell">{res.score.toFixed(4)}</td>
                                                            </tr>
                                                        );
                                                    })}
                                                </tbody>
                                            </table>
                                        </div>
                                        <div className="audit-footer">
                                            <span>⚡ Optimized with MS-Marco MiniLM-L6</span>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}

                    {loading && (
                        <div className="message-wrapper assistant loading">
                            <div className="author-info">
                                <div className="avatar">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z"></path><path d="M12 6v6l4 2"></path></svg>
                                </div>
                            </div>
                            <div className="message-body">
                                <div className="typing-indicator">
                                    <span></span><span></span><span></span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}
            <div ref={messagesEndRef} />
        </div>
    );
}

export default MessageList;
