import { useState, useRef, useEffect } from 'react';
import { Paperclip, Plus, Mic, ArrowUp } from 'lucide-react';
import './ChatInput.css';

function ChatInput({ onSend, disabled }) {
    const [message, setMessage] = useState('');
    const textareaRef = useRef(null);
    const hasText = message.trim().length > 0;

    const handleSubmit = (e) => {
        e.preventDefault();
        if (hasText && !disabled) {
            onSend(message);
            setMessage('');
            if (textareaRef.current) {
                textareaRef.current.style.height = 'auto';
            }
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
        }
    };

    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
        }
    }, [message]);

    return (
        <form className="chat-input-form" onSubmit={handleSubmit}>
            <div className={`prompt-bar ${hasText ? 'has-text' : ''}`}>

                {/* Left icons */}
                <button type="button" className="prompt-icon-btn" title="Attach file" tabIndex={0}>
                    <Paperclip size={20} strokeWidth={1.8} />
                </button>
                <button type="button" className="prompt-icon-btn" title="Tools" tabIndex={0}>
                    <Plus size={20} strokeWidth={1.8} />
                </button>

                {/* Text input */}
                <textarea
                    ref={textareaRef}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask anything"
                    disabled={disabled}
                    rows="1"
                    className="prompt-textarea"
                />

                {/* Right icons */}
                <button type="button" className="prompt-icon-btn" title="Voice input" tabIndex={0}>
                    <Mic size={20} strokeWidth={1.8} />
                </button>

                <button
                    type="submit"
                    className={`prompt-send-btn ${hasText ? 'active' : ''}`}
                    disabled={disabled || !hasText}
                    title="Send message"
                    tabIndex={0}
                >
                    <ArrowUp size={18} strokeWidth={2.5} />
                </button>
            </div>
        </form>
    );
}

export default ChatInput;
