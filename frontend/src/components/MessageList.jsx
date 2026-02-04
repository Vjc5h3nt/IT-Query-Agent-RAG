import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import './MessageList.css';

function MessageList({ messages, sources, onRegenerate, loading, userName }) {
    const messagesEndRef = useRef(null);
    const [copiedIndex, setCopiedIndex] = useState(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, loading]);

    const formatTime = (timestamp) => {
        if (!timestamp) return '';
        const date = new Date(timestamp);
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    const handleCopy = (content, index) => {
        navigator.clipboard.writeText(content).then(() => {
            setCopiedIndex(index);
            setTimeout(() => setCopiedIndex(null), 2000);
        });
    };

    return (
        <div className="message-list">
            {messages.length === 0 && !loading ? (
                <div className="empty-state">
                    <h3>How can I help you today?</h3>
                    <p>Start chatting about your documents.</p>
                </div>
            ) : (
                <div className="messages-container">
                    {messages.map((msg, index) => (
                        <div key={index} className={`message-wrapper ${msg.role}`}>
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
                            <div className="message-body">
                                <div className="message-text">
                                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                                </div>
                                {msg.sources && msg.sources.length > 0 && (
                                    <div className="message-sources">
                                        <div className="sources-title">Sources</div>
                                        <div className="sources-list">
                                            {msg.sources.map((source, i) => (
                                                <div key={i} className="source-tag">{source}</div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
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
                                            title={copiedIndex === index ? "Copied!" : "Copy message"}
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
                                    <span></span>
                                    <span></span>
                                    <span></span>
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
