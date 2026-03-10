import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
    Plus,
    Search,
    MessageSquare,
    BookOpen,
    Folder,
    Trash2,
    Moon,
    Sun,
    ChevronLeft,
    ChevronRight,
    Pencil,
    Info,
    X,
    MoreHorizontal,
    PanelLeftOpen,
} from 'lucide-react';
import catLogo from '../assets/cat.png';
import catLogoWhite from '../assets/cat-white.png';
import './Sidebar.css';

/* ── Tooltip (collapsed rail labels) ── */
function Tooltip({ label, children }) {
    return (
        <div className="tooltip-wrapper">
            {children}
            <span className="tooltip-label">{label}</span>
        </div>
    );
}

/* ── Portal dropdown (escapes overflow:hidden) ── */
function SessionDropdown({ anchorRect, onRename, onDelete, onClose }) {
    const ref = useRef(null);

    useEffect(() => {
        const handle = (e) => {
            if (ref.current && !ref.current.contains(e.target)) onClose();
        };
        document.addEventListener('mousedown', handle);
        return () => document.removeEventListener('mousedown', handle);
    }, [onClose]);

    if (!anchorRect) return null;

    const MENU_WIDTH = 160;
    const MENU_HEIGHT = 88;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let top = anchorRect.bottom + 4;
    let left = anchorRect.right - MENU_WIDTH;
    if (top + MENU_HEIGHT > vh) top = anchorRect.top - MENU_HEIGHT - 4;
    if (left < 8) left = 8;
    if (left + MENU_WIDTH > vw - 8) left = vw - MENU_WIDTH - 8;

    return createPortal(
        <div
            ref={ref}
            className="session-dropdown"
            style={{ position: 'fixed', top, left, width: MENU_WIDTH, zIndex: 9999 }}
            onMouseDown={(e) => e.stopPropagation()}
        >
            <button className="session-dropdown-item" onClick={onRename}>
                <Pencil size={14} strokeWidth={2} />
                Rename
            </button>
            <button className="session-dropdown-item danger" onClick={onDelete}>
                <Trash2 size={14} strokeWidth={2} />
                Delete
            </button>
        </div>,
        document.body
    );
}

/* ── Main component ── */
function Sidebar({
    sessions,
    currentSession,
    onSelectSession,
    onNewSession,
    onDeleteSession,
    onDeleteAllSessions,
    onDeleteVectorStore,
    onJiraIngest,
    onIngest,
    searchQuery,
    onSearchChange,
    isCollapsed,
    onToggleCollapse,
    theme,
    onToggleTheme,
    userName,
    onUpdateUserName,
    onRenameSession,
}) {
    const [isEditingName, setIsEditingName]     = useState(false);
    const [tempName, setTempName]               = useState(userName);
    const [editingSessionId, setEditingSessionId]       = useState(null);
    const [editingSessionValue, setEditingSessionValue] = useState('');
    const [showSystemDetails, setShowSystemDetails]     = useState(false);
    const [menuAnchor, setMenuAnchor] = useState(null); // { id, rect }

    /* ── helpers ── */
    const getInitials = (name = '') => {
        const words = name.trim().split(/\s+/).filter(Boolean);
        if (!words.length) return '?';
        if (words.length === 1) return words[0][0].toUpperCase();
        return (words[0][0] + words[words.length - 1][0]).toUpperCase();
    };

    const PALETTE = [
        '#E05A5A','#E07A2F','#C4882D','#3AAD77',
        '#4A90D9','#7C6ED4','#D4609A','#2BB8A8',
        '#5B7FA6','#8E6B3E',
    ];
    const getAvatarColor = (name = '') => {
        let h = 0;
        for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
        return PALETTE[Math.abs(h) % PALETTE.length];
    };

    const handleStartEdit   = () => { setTempName(userName); setIsEditingName(true); };
    const handleSaveName    = () => { if (tempName.trim()) onUpdateUserName(tempName.trim()); setIsEditingName(false); };
    const handleNameKeyDown = (e) => { if (e.key === 'Enter') handleSaveName(); if (e.key === 'Escape') setIsEditingName(false); };

    const startEditingSession = (sessionId, name) => {
        setEditingSessionId(sessionId);
        setEditingSessionValue(name);
    };
    const saveSessionName = (sessionId) => {
        const original = sessions.find(s => s.id === sessionId)?.name;
        if (editingSessionValue.trim() && editingSessionValue !== original)
            onRenameSession(sessionId, editingSessionValue.trim());
        setEditingSessionId(null);
    };

    const openMenu = useCallback((e, session) => {
        e.stopPropagation();
        const rect = e.currentTarget.getBoundingClientRect();
        setMenuAnchor(prev => prev?.id === session.id ? null : { id: session.id, rect, session });
    }, []);

    const closeMenu = useCallback(() => setMenuAnchor(null), []);

    /* ── Tool button (expanded + collapsed) ── */
    const ToolBtn = ({ icon, label, onClick, className = '' }) =>
        isCollapsed ? (
            <Tooltip label={label}>
                <button className={`btn-tool ${className}`} onClick={onClick}>{icon}</button>
            </Tooltip>
        ) : (
            <button className={`btn-tool ${className}`} onClick={onClick}>
                {icon}
                <span className="btn-tool-label">{label}</span>
            </button>
        );

    return (
        <div className={`sidebar-container ${isCollapsed ? 'collapsed' : ''}`}>
            <div className="sidebar">

                {/* ── Brand / Logo ── */}
                {isCollapsed ? (
                    /* Collapsed: cat logo fades to expand icon on hover — single button, no overlap */
                    <div className="sidebar-brand collapsed">
                        <button
                            className="brand-collapse-btn"
                            onClick={onToggleCollapse}
                            title="Expand sidebar"
                            aria-label="Expand sidebar"
                        >
                            <img src={theme === 'light' ? catLogoWhite : catLogo} alt="logo" className="brand-cat-img" />
                            <PanelLeftOpen size={20} strokeWidth={2} className="brand-expand-icon" />
                        </button>
                    </div>
                ) : (
                    /* Expanded: logo + dim name + collapse button */
                    <div className="sidebar-brand">
                        <div className="brand-logo-wrap">
                            <div className="brand-logo">
                                <img src={theme === 'light' ? catLogoWhite : catLogo} alt="logo" className="brand-cat-img" />
                            </div>
                            <span className="brand-name-dim">IT Query Agent</span>
                        </div>
                        <button
                            className="btn-collapse"
                            onClick={onToggleCollapse}
                            title="Collapse sidebar"
                        >
                            <ChevronLeft size={18} strokeWidth={2} />
                        </button>
                    </div>
                )}

                {/* ── Header actions ── */}
                <div className="sidebar-header">
                    {isCollapsed ? (
                        <Tooltip label="New Chat">
                            <button className="btn-new-chat icon-only" onClick={onNewSession}>
                                <Plus size={18} strokeWidth={2} />
                            </button>
                        </Tooltip>
                    ) : (
                        <button className="btn-new-chat" onClick={onNewSession}>
                            <Plus size={18} strokeWidth={2} />
                            <span>New Chat</span>
                        </button>
                    )}

                    {isCollapsed ? (
                        <Tooltip label="Search">
                            <button className="btn-icon-only" onClick={() => {}}>
                                <Search size={18} strokeWidth={2} />
                            </button>
                        </Tooltip>
                    ) : (
                        <div className="search-bar">
                            <Search size={18} color="#6B7280" strokeWidth={2} />
                            <input
                                type="text"
                                placeholder="Search conversations..."
                                value={searchQuery}
                                onChange={(e) => onSearchChange(e.target.value)}
                            />
                        </div>
                    )}
                </div>

                {/* ── Conversations ── */}
                {!isCollapsed && (
                    <div className="sidebar-conversations">
                        <p className="section-label">Conversations</p>
                        <div className="sessions-list">
                            {sessions.length === 0 ? (
                                <div className="no-sessions">No conversations yet</div>
                            ) : (
                                sessions.map((session) => {
                                    const isActive  = currentSession?.id === session.id;
                                    const isEditing = editingSessionId === session.id;
                                    const menuOpen  = menuAnchor?.id === session.id;

                                    return (
                                        <div
                                            key={session.id}
                                            className={`session-item ${isActive ? 'active' : ''} ${menuOpen ? 'menu-open' : ''}`}
                                            onClick={() => onSelectSession(session.id)}
                                        >
                                            <MessageSquare size={18} strokeWidth={2} className="session-icon-svg" />

                                            {isEditing ? (
                                                <input
                                                    autoFocus
                                                    className="session-name-edit"
                                                    value={editingSessionValue}
                                                    onChange={(e) => setEditingSessionValue(e.target.value)}
                                                    onBlur={() => saveSessionName(session.id)}
                                                    onKeyDown={(e) => {
                                                        if (e.key === 'Enter')  saveSessionName(session.id);
                                                        if (e.key === 'Escape') setEditingSessionId(null);
                                                    }}
                                                    onClick={(e) => e.stopPropagation()}
                                                />
                                            ) : (
                                                <>
                                                    <span className="session-name">{session.name}</span>
                                                    <button
                                                        className="session-more-btn"
                                                        onClick={(e) => openMenu(e, session)}
                                                        title="More options"
                                                    >
                                                        <MoreHorizontal size={16} strokeWidth={2} />
                                                    </button>
                                                </>
                                            )}
                                        </div>
                                    );
                                })
                            )}
                        </div>
                    </div>
                )}

                {/* ── Tools ── */}
                <div className="sidebar-tools">
                    {!isCollapsed && <p className="section-label">Tools</p>}
                    <ToolBtn icon={<BookOpen size={18} strokeWidth={2} />} label="Ingest Documents"    onClick={onIngest} />
                    <ToolBtn icon={<Folder   size={18} strokeWidth={2} />} label="Ingest JIRA XML"     onClick={onJiraIngest} />
                    <ToolBtn icon={<Trash2   size={18} strokeWidth={2} />} label="Manage Vector Stores" onClick={onDeleteVectorStore} className="danger-hover" />
                </div>

                {/* ── Footer ── */}
                <div className="sidebar-footer">
                    {isCollapsed ? (
                        <Tooltip label={userName}>
                            <div className="user-profile icon-only">
                                <div className="avatar avatar-initials" style={{ background: getAvatarColor(userName) }}>
                                    <span>{getInitials(userName)}</span>
                                </div>
                            </div>
                        </Tooltip>
                    ) : (
                        <div className="user-profile">
                            <div className="avatar avatar-initials" style={{ background: getAvatarColor(userName) }}>
                                <span>{getInitials(userName)}</span>
                            </div>
                            <div className="user-info">
                                {isEditingName ? (
                                    <input
                                        autoFocus
                                        className="name-edit-input"
                                        value={tempName}
                                        onChange={(e) => setTempName(e.target.value)}
                                        onBlur={handleSaveName}
                                        onKeyDown={handleNameKeyDown}
                                    />
                                ) : (
                                    <span className="user-name" onClick={handleStartEdit} title="Click to rename">
                                        {userName}
                                    </span>
                                )}
                            </div>
                            <button className="action-icon info-btn" onClick={() => setShowSystemDetails(true)} title="System Details">
                                <Info size={16} strokeWidth={2} />
                            </button>
                        </div>
                    )}

                    {isCollapsed ? (
                        <Tooltip label={theme === 'light' ? 'Dark Mode' : 'Light Mode'}>
                            <button className="btn-theme icon-only" onClick={onToggleTheme}>
                                {theme === 'light' ? <Moon size={18} strokeWidth={2} /> : <Sun size={18} strokeWidth={2} />}
                            </button>
                        </Tooltip>
                    ) : (
                        <button className="btn-theme" onClick={onToggleTheme}>
                            <span className="theme-label">
                                {theme === 'light' ? <Moon size={18} strokeWidth={2} /> : <Sun size={18} strokeWidth={2} />}
                                {theme === 'light' ? 'Dark Mode' : 'Light Mode'}
                            </span>
                            <span className={`theme-switch ${theme === 'dark' ? 'on' : ''}`}>
                                <span className="theme-thumb" />
                            </span>
                        </button>
                    )}
                </div>
            </div>

            {/* ── Portal dropdown (outside overflow:hidden) ── */}
            {menuAnchor && (
                <SessionDropdown
                    anchorRect={menuAnchor.rect}
                    onClose={closeMenu}
                    onRename={() => {
                        startEditingSession(menuAnchor.id, menuAnchor.session.name);
                        closeMenu();
                    }}
                    onDelete={() => {
                        onDeleteSession(menuAnchor.id);
                        closeMenu();
                    }}
                />
            )}

            {/* ── System Details Modal ── */}
            {showSystemDetails && (
                <div className="modal-overlay" onClick={() => setShowSystemDetails(false)}>
                    <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                        <div className="modal-header">
                            <h3>System Details</h3>
                            <button className="modal-close" onClick={() => setShowSystemDetails(false)}>
                                <X size={18} strokeWidth={2} />
                            </button>
                        </div>
                        <div className="modal-body">
                            <table className="system-details-table">
                                <tbody>
                                    {[
                                        ['Language Model',      'Claude 3 Haiku (AWS Bedrock)'],
                                        ['Temperature',         '0.1 (High Precision)'],
                                        ['Embeddings',          'Amazon Titan Text v1 (1536D)'],
                                        ['Vector Store',        'ChromaDB (L2 Distance)'],
                                        ['Similarity Threshold','0.7'],
                                        ['Reranker',            'ms-marco-MiniLM-L-12-v2'],
                                        ['Retrieval Pipeline',  'JIRA: Hybrid + Reranking | PDF: Docling + Reranking'],
                                        ['Backend',             'FastAPI (Python 3.11+)'],
                                        ['Session Storage',     'SQLite'],
                                        ['Memory Window',       '5 messages'],
                                        ['Frontend',            'React 18 + Vite'],
                                    ].map(([k, v]) => (
                                        <tr key={k}>
                                            <td className="detail-category">{k}</td>
                                            <td className="detail-value">{v}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default Sidebar;
