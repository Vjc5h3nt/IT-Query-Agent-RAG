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
                    <h3 className="session-title">{session ? session.name : 'New Conversation'}</h3>
                </div>
                <div className="chat-controls">
                    <div
                        className={`kb-toggle ${useKnowledgeBase ? 'enabled' : ''}`}
                        onClick={onToggleKnowledgeBase}
                        title={useKnowledgeBase ? "Knowledge Base ON" : "Knowledge Base OFF"}
                    >
                        <span className="kb-icon">📚</span>
                        <span className="kb-text">Knowledge Base</span>
                        <div className="toggle-switch">
                            <div className="toggle-knob"></div>
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
