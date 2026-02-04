import { useState } from 'react';
import './Sidebar.css';

function Sidebar({
    sessions,
    currentSession,
    onSelectSession,
    onNewSession,
    onDeleteSession,
    onDeleteAllSessions,
    onIngest,
    searchQuery,
    onSearchChange,
    isCollapsed,
    onToggleCollapse,
    theme,
    onToggleTheme,
    userName,
    onUpdateUserName
}) {
    const [isSearchVisible, setIsSearchVisible] = useState(false);
    const [isEditingName, setIsEditingName] = useState(false);
    const [tempName, setTempName] = useState(userName);

    const handleStartEdit = () => {
        setTempName(userName);
        setIsEditingName(true);
    };

    const handleSaveName = () => {
        if (tempName.trim()) {
            onUpdateUserName(tempName.trim());
        }
        setIsEditingName(false);
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') handleSaveName();
        if (e.key === 'Escape') setIsEditingName(false);
    };

    return (
        <div className={`sidebar-container ${isCollapsed ? 'collapsed' : ''}`}>
            <button className="btn-toggle-sidebar" onClick={onToggleCollapse} title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}>
                {isCollapsed ? '→' : '←'}
            </button>
            <div className="sidebar">
                <div className="sidebar-header">
                    <div className="brand">
                        <span className="brand-text">IT Query Agent</span>
                    </div>
                    {!isCollapsed && (
                        <div className="header-actions">
                            <button className="btn-new-session" onClick={onNewSession}>
                                <span className="plus-icon">+</span> New chat
                            </button>
                            <div className={`search-wrapper ${isSearchVisible ? 'visible' : ''}`}>
                                <button className="btn-search" onClick={() => setIsSearchVisible(!isSearchVisible)}>
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                                </button>
                                {isSearchVisible && (
                                    <input
                                        type="text"
                                        placeholder="Search sessions..."
                                        value={searchQuery}
                                        onChange={(e) => onSearchChange(e.target.value)}
                                        autoFocus
                                    />
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {!isCollapsed && (
                    <>
                        <div className="sidebar-conversations">
                            <div className="section-header">
                                <span>Your conversations</span>
                            </div>
                            <div className="sessions-list">
                                {sessions.length === 0 ? (
                                    <div className="no-sessions">No conversations found</div>
                                ) : (
                                    sessions.map((session) => (
                                        <div
                                            key={session.id}
                                            className={`session-item ${currentSession?.id === session.id ? 'active' : ''}`}
                                            onClick={() => onSelectSession(session.id)}
                                        >
                                            <div className="session-name">{session.name}</div>
                                            <div className="session-actions">
                                                <button className="action-btn delete" onClick={(e) => { e.stopPropagation(); onDeleteSession(session.id); }} title="Delete session">
                                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                                                </button>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>

                        <div className="sidebar-footer">
                            <div className="user-profile">
                                <div className="avatar">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                                </div>
                                <div className="user-info">
                                    {isEditingName ? (
                                        <input
                                            autoFocus
                                            className="name-edit-input"
                                            value={tempName}
                                            onChange={(e) => setTempName(e.target.value)}
                                            onBlur={handleSaveName}
                                            onKeyDown={handleKeyDown}
                                        />
                                    ) : (
                                        <div className="user-name-wrapper" onClick={handleStartEdit}>
                                            <div className="user-name">{userName}</div>
                                            <button className="action-btn edit-name" title="Edit name">
                                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </div>
                            <button className="btn-toggle-theme" onClick={onToggleTheme} title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}>
                                {theme === 'light' ? (
                                    <><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg> Dark Mode</>
                                ) : (
                                    <><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg> Light Mode</>
                                )}
                            </button>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

export default Sidebar;
