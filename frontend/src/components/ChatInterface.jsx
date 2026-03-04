/**
 * Chat interface component
 */
import { useState, useEffect } from 'react';
import MessageList from './MessageList';
import ChatInput from './ChatInput';
import './ChatInterface.css';

function ChatInterface({ session, onSendMessage, useKnowledgeBase, onToggleKnowledgeBase, userName }) {
    const [messages, setMessages] = useState([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (session) {
            setMessages(session.messages || []);
        } else {
            setMessages([]);
        }
    }, [session]);

    const handleSendMessage = async (message, skipAddUser = false) => {
        if (!session) return;

        setLoading(true);

        if (!skipAddUser) {
            const userMessage = {
                role: 'user',
                content: message,
                timestamp: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, userMessage]);
        }

        try {
            const response = await onSendMessage(message);

            const assistantMessage = {
                role: 'assistant',
                content: response.assistant_message.content,
                timestamp: response.assistant_message.timestamp,
                sources: response.sources,
                rerank_summary: response.rerank_summary,
                metrics: response.metrics,
                citations: response.citations,
            };

            setMessages((prev) => [...prev, assistantMessage]);
        } catch (error) {
            console.error('Error sending message:', error);
            const errorMessage = {
                role: 'assistant',
                content: 'Sorry, there was an error processing your message. Please try again.',
                timestamp: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, errorMessage]);
        } finally {
            setLoading(false);
        }
    };

    const handleRegenerate = async (index) => {
        const lastUserMessageIndex = messages.findLastIndex((m, i) => i < index && m.role === 'user');
        if (lastUserMessageIndex !== -1) {
            const lastUserMessage = messages[lastUserMessageIndex].content;
            handleSendMessage(lastUserMessage, true);
        }
    };



    return (
        <div className="chat-interface">
            <div className="chat-header">
                <div className="header-left">
                    <div className="header-indicator">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                        </svg>
                    </div>
                    <h3 className="session-title">{session ? session.name : 'New Chat'}</h3>
                </div>

                <div className="chat-actions">
                    <div
                        className={`kb-switch ${useKnowledgeBase ? 'active' : ''}`}
                        onClick={onToggleKnowledgeBase}
                        title={useKnowledgeBase ? "Search is grounded in Knowledge Base" : "Search is general"}
                    >
                        <div className="kb-switch-label">
                            <svg className="kb-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                                <line x1="8" y1="21" x2="16" y2="21"></line>
                                <line x1="12" y1="17" x2="12" y2="21"></line>
                            </svg>
                            <span>Knowledge Base</span>
                        </div>
                        <div className="kb-switch-track">
                            <div className="kb-switch-thumb"></div>
                        </div>
                    </div>
                </div>
            </div>
            <MessageList
                messages={messages}
                onRegenerate={handleRegenerate}
                loading={loading}
                userName={userName}
            />
            <div className="input-wrapper">
                <ChatInput onSend={handleSendMessage} disabled={loading} />
            </div>
        </div>
    );
}

export default ChatInterface;
