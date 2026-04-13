/**
 * Chat interface component
 */
import { useState, useEffect } from 'react';
import MessageList from './MessageList';
import ChatInput from './ChatInput';
import './ChatInterface.css';

function ChatInterface({ session, onSendMessage, userName, onOpenSidebar }) {
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
                    {onOpenSidebar && (
                        <button className="mobile-menu-btn" onClick={onOpenSidebar} aria-label="Open sidebar">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
                        </button>
                    )}
                    <div className="header-indicator">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                        </svg>
                    </div>
                    <h3 className="session-title">{session ? session.name : 'New Chat'}</h3>
                </div>
            </div>
            <MessageList
                messages={messages}
                onRegenerate={handleRegenerate}
                loading={loading}
                userName={userName}
                sessionId={session?.id}
            />
            <div className="input-wrapper">
                <ChatInput onSend={handleSendMessage} disabled={loading} />
            </div>
        </div>
    );
}

export default ChatInterface;
