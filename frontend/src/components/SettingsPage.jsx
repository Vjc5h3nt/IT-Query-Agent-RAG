import { useState, useEffect } from 'react';
import { BookOpen, Folder, Trash2, Brain, ToggleLeft, ToggleRight, Info, Cpu, Database, MessageSquare, ChevronRight, ArrowLeft } from 'lucide-react';
import * as api from '../services/api';
import './SettingsPage.css';

function SettingsPage({
    onIngest,
    onJiraIngest,
    onDeleteVectorStore,
    useReranking,
    onToggleReranking,
    contextMessages,
    onContextMessagesChange,
    onBackToChat,
    onOpenSidebar,
}) {
    const [serverSettings, setServerSettings] = useState(null);

    useEffect(() => {
        api.getServerSettings()
            .then(setServerSettings)
            .catch(() => setServerSettings(null));
    }, []);

    const getContextLabel = (val) => {
        if (val <= 1)  return 'Minimal';
        if (val <= 3)  return 'Light';
        if (val <= 5)  return 'Default';
        if (val <= 10) return 'Extended';
        if (val <= 15) return 'Deep';
        if (val <= 20) return 'Very Deep';
        return 'Maximum';
    };

    const getUsageLevel = (val) => {
        if (val <= 5)  return 'low';
        if (val <= 15) return 'moderate';
        return 'high';
    };

    const sliderPercent = ((contextMessages - 1) / (25 - 1)) * 100;

    return (
        <div className="settings-page">
            <div className="settings-container">

                <div className="settings-header">
                    <div className="settings-header-nav">
                        {onOpenSidebar && (
                            <button className="mobile-menu-btn" onClick={onOpenSidebar} aria-label="Open sidebar">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
                            </button>
                        )}
                        <button className="settings-back-btn" onClick={onBackToChat}>
                            <ArrowLeft size={16} strokeWidth={2} />
                            <span>Back to Chat</span>
                        </button>
                    </div>
                    <h2>Settings</h2>
                    <p className="settings-subtitle">Configure your RAG pipeline, manage data stores, and adjust chat preferences.</p>
                </div>

                {/* ── Chat Preferences ─────────────────────────── */}
                <section className="settings-section">
                    <div className="section-title">
                        <MessageSquare size={16} />
                        <h3>Chat Preferences</h3>
                    </div>

                    <div className="setting-card">
                        <div className="setting-row">
                            <div className="setting-info">
                                <span className="setting-label">Cross-Encoder Reranking</span>
                                <span className="setting-desc">Rerank retrieved documents for higher precision (slower)</span>
                            </div>
                            <button
                                className={`toggle-btn ${useReranking ? 'active' : ''}`}
                                onClick={onToggleReranking}
                                aria-label="Toggle Reranking"
                            >
                                {useReranking ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
                            </button>
                        </div>

                        <div className="setting-divider" />

                        <div className="setting-row column">
                            <div className="setting-info">
                                <span className="setting-label">
                                    <Brain size={16} />
                                    Conversation Memory
                                </span>
                                <span className="setting-desc">
                                    Number of conversation turns sent to the LLM as context. Higher values improve continuity but increase latency.
                                </span>
                            </div>
                            <div className="slider-group">
                                <div className="slider-track-wrapper">
                                    <div className="slider-track-fill" style={{ width: `${sliderPercent}%` }} />
                                    <input
                                        type="range"
                                        min={1}
                                        max={25}
                                        step={1}
                                        value={contextMessages}
                                        onChange={(e) => onContextMessagesChange(Number(e.target.value))}
                                        className="settings-range"
                                    />
                                </div>
                                <div className="slider-labels">
                                    <span>1</span>
                                    <span className="slider-current">
                                        {contextMessages} turns &middot; {getContextLabel(contextMessages)}
                                    </span>
                                    <span>25</span>
                                </div>
                                <div className="slider-hint">
                                    <Info size={12} />
                                    <span>
                                        {contextMessages * 2} messages &middot;{' '}
                                        <span className={`usage-text ${getUsageLevel(contextMessages)}`}>
                                            {getUsageLevel(contextMessages)} token usage
                                        </span>
                                        {contextMessages > 15 && ' — may increase response time'}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                {/* ── Data Management ──────────────────────────── */}
                <section className="settings-section">
                    <div className="section-title">
                        <Database size={16} />
                        <h3>Data Management</h3>
                    </div>

                    <div className="tool-cards">
                        <button className="tool-card" onClick={onIngest}>
                            <div className="tool-card-icon ingest">
                                <BookOpen size={20} />
                            </div>
                            <div className="tool-card-body">
                                <span className="tool-card-title">Ingest Documents</span>
                                <span className="tool-card-desc">Process PDF, DOCX, TXT, and MD files into the vector store</span>
                            </div>
                            <ChevronRight size={16} className="tool-card-arrow" />
                        </button>

                        <button className="tool-card" onClick={onJiraIngest}>
                            <div className="tool-card-icon jira">
                                <Folder size={20} />
                            </div>
                            <div className="tool-card-body">
                                <span className="tool-card-title">Ingest JIRA XML</span>
                                <span className="tool-card-desc">Upload and process JIRA exports with the interactive pipeline</span>
                            </div>
                            <ChevronRight size={16} className="tool-card-arrow" />
                        </button>

                        <button className="tool-card danger" onClick={onDeleteVectorStore}>
                            <div className="tool-card-icon delete">
                                <Trash2 size={20} />
                            </div>
                            <div className="tool-card-body">
                                <span className="tool-card-title">Manage Vector Stores</span>
                                <span className="tool-card-desc">View counts and delete JIRA or PDF vector collections</span>
                            </div>
                            <ChevronRight size={16} className="tool-card-arrow" />
                        </button>
                    </div>
                </section>

                {/* ── System Information ───────────────────────── */}
                <section className="settings-section">
                    <div className="section-title">
                        <Cpu size={16} />
                        <h3>System Information</h3>
                    </div>

                    <div className="system-grid">
                        {[
                            ['LLM', serverSettings?.llm_model],
                            ['Embeddings', serverSettings?.embedding_model],
                            ['Temperature', serverSettings?.llm_temperature],
                            ['Max Tokens', serverSettings?.llm_max_tokens],
                            ['Top K', serverSettings?.top_k_results],
                            ['Threshold', serverSettings?.similarity_threshold],
                            ['Chunk / Overlap', serverSettings ? `${serverSettings.chunk_size} / ${serverSettings.chunk_overlap}` : null],
                            ['Memory Default', serverSettings ? `${serverSettings.max_memory_messages} turns` : null],
                        ].map(([key, val]) => (
                            <div className="system-item" key={key}>
                                <span className="system-key">{key}</span>
                                <span className="system-val">{val ?? '...'}</span>
                            </div>
                        ))}
                    </div>
                </section>
            </div>
        </div>
    );
}

export default SettingsPage;
