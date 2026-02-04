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
            // Load session messages
            setMessages(session.messages || []);
        } else {
            setMessages([]);
        }
    }, [session]);

    const handleSendMessage = async (message, skipAddUser = false) => {
        if (!session) return;

        setLoading(true);

        if (!skipAddUser) {
            // Add user message immediately
            const userMessage = {
                role: 'user',
                content: message,
                timestamp: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, userMessage]);
        }

        try {
            const response = await onSendMessage(message);

            // Add assistant message with sources
            const assistantMessage = {
                role: 'assistant',
                content: response.assistant_message.content,
                timestamp: response.assistant_message.timestamp,
                sources: response.sources,
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
        // Find the user message before this assistant message
        const lastUserMessageIndex = messages.findLastIndex((m, i) => i < index && m.role === 'user');
        if (lastUserMessageIndex !== -1) {
            const lastUserMessage = messages[lastUserMessageIndex].content;
            handleSendMessage(lastUserMessage, true); // true = skipAddUser
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
                        <span className="kb-text">Knowlege Base</span>
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
