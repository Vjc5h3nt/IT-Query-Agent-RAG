/**
 * Main App component
 */
import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import SettingsPage from './components/SettingsPage';
import IngestionModal from './components/IngestionModal';
import DeleteVectorModal from './components/DeleteVectorModal';
import JiraIngestModal from './components/JiraIngestModal';
import * as api from './services/api';
import './App.css';

function App() {
  const [sessions, setSessions] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [loading, setLoading] = useState(true);

  // View state: 'chat' or 'settings'
  const [activeView, setActiveView] = useState('chat');

  // Ingestion state
  const [ingestionModalOpen, setIngestionModalOpen] = useState(false);
  const [ingestionStatus, setIngestionStatus] = useState(null);
  const [ingestionStats, setIngestionStats] = useState(null);

  // Vector Store Deletion state
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState('idle');

  // JIRA ingestion state
  const [jiraModalOpen, setJiraModalOpen] = useState(false);

  // UI State: Theme and User Name
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('theme') ||
      (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  });

  const [userName, setUserName] = useState(() => {
    return localStorage.getItem('userName') || 'User';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem('userName', userName);
  }, [userName]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  // Chat preferences
  const [useReranking, setUseReranking] = useState(false);
  const [contextMessages, setContextMessages] = useState(() => {
    const saved = localStorage.getItem('contextMessages');
    return saved ? parseInt(saved, 10) : 5;
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => window.innerWidth < 768);
  const [emptySessionId, setEmptySessionId] = useState(null);

  // Auto-collapse sidebar on mobile resize
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    const handler = (e) => setIsSidebarCollapsed(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  useEffect(() => {
    localStorage.setItem('contextMessages', contextMessages.toString());
  }, [contextMessages]);

  const loadSessions = async () => {
    try {
      const data = await api.getSessions();
      setSessions(Array.isArray(data) ? data : []);
      setLoading(false);
    } catch (error) {
      console.error('Error loading sessions:', error);
      setLoading(false);
    }
  };

  // Load sessions on mount
  useEffect(() => {
    loadSessions();
  }, []);

  const handleNewSession = async () => {
    // Switch to chat view when creating a new session
    setActiveView('chat');

    if (emptySessionId && sessions.some((s) => s.id === emptySessionId)) {
      await handleSelectSession(emptySessionId);
      return;
    }

    if (currentSession && (currentSession.messages?.length ?? 0) === 0) {
      return;
    }

    try {
      const newSession = await api.createSession();
      setSessions((prev) => [newSession, ...prev]);

      const sessionDetail = await api.getSession(newSession.id);
      setCurrentSession(sessionDetail);
      setEmptySessionId(newSession.id);
    } catch (error) {
      console.error('Error creating session:', error);
      alert('Failed to create session');
    }
  };

  const handleSelectSession = async (sessionId) => {
    setActiveView('chat');
    // Auto-collapse sidebar on mobile after selection
    if (window.innerWidth < 768) setIsSidebarCollapsed(true);
    try {
      const sessionDetail = await api.getSession(sessionId);
      setCurrentSession(sessionDetail);
    } catch (error) {
      console.error('Error loading session:', error);
      alert('Failed to load session');
    }
  };

  const handleDeleteSession = async (sessionId) => {
    try {
      await api.deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));

      if (currentSession?.id === sessionId) {
        setCurrentSession(null);
      }
      if (emptySessionId === sessionId) {
        setEmptySessionId(null);
      }
    } catch (error) {
      console.error('Error deleting session:', error);
      alert('Failed to delete session');
    }
  };

  const handleRenameSession = async (sessionId, newName) => {
    try {
      const updated = await api.updateSession(sessionId, newName);
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, name: updated.name } : s))
      );
      if (currentSession?.id === sessionId) {
        setCurrentSession((prev) => ({ ...prev, name: updated.name }));
      }
    } catch (error) {
      console.error('Error renaming session:', error);
      alert('Failed to rename session');
    }
  };

  const handleSendMessage = async (message) => {
    if (!currentSession) return;

    if (currentSession.id === emptySessionId) {
      setEmptySessionId(null);
    }

    const response = await api.sendMessage(
      currentSession.id,
      message,
      true,
      useReranking,
      contextMessages
    );

    loadSessions();
    return response;
  };

  const handleDeleteAllSessions = async () => {
    if (window.confirm('Are you sure you want to delete ALL chat sessions? This cannot be undone.')) {
      try {
        await api.deleteAllSessions();
        setSessions([]);
        setCurrentSession(null);
      } catch (error) {
        console.error('Error deleting all sessions:', error);
        alert('Failed to delete all sessions');
      }
    }
  };

  const handleDeleteVectorStore = () => {
    setDeleteModalOpen(true);
    setDeleteStatus('idle');
  };

  const handleOpenIngestModal = () => {
    setIngestionModalOpen(true);
    setIngestionStatus(null);
    setIngestionStats(null);
  };

  const handleIngestWithStrategy = async () => {
    setIngestionStatus('processing');

    const settings = {
      chunk_size: 400,
      chunk_overlap: 100,
      top_k_stage1: 50,
      rerank_top_k: 8,
      max_memory_messages: 12
    };

    setUseReranking(true);

    try {
      const result = await api.ingestDocuments(settings);
      setIngestionStatus('complete');
      setIngestionStats(result);
    } catch (error) {
      console.error('Error ingesting documents:', error);
      setIngestionStatus('error');
      setIngestionStats({ error: error.response?.data?.detail || error.message || 'Failed to ingest documents' });
    }
  };

  const closeIngestionModal = () => {
    if (ingestionStatus === 'processing') return;
    setIngestionModalOpen(false);
    setIngestionStatus(null);
    setIngestionStats(null);
  };

  const filteredSessions = sessions.filter(session =>
    session.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (loading) {
    return (
      <div className="app loading-screen">
        <div className="loading-content">
          <div className="spinner"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`app ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Sidebar
        sessions={filteredSessions}
        currentSession={currentSession}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onDeleteSession={handleDeleteSession}
        onRenameSession={handleRenameSession}
        onDeleteAllSessions={handleDeleteAllSessions}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
        theme={theme}
        onToggleTheme={toggleTheme}
        userName={userName}
        onUpdateUserName={setUserName}
        activeView={activeView}
        onOpenSettings={() => setActiveView('settings')}
      />
      <div className="main-content">
        {activeView === 'settings' ? (
          <SettingsPage
            onIngest={handleOpenIngestModal}
            onJiraIngest={() => setJiraModalOpen(true)}
            onDeleteVectorStore={handleDeleteVectorStore}
            useReranking={useReranking}
            onToggleReranking={() => setUseReranking(!useReranking)}
            contextMessages={contextMessages}
            onContextMessagesChange={setContextMessages}
            onBackToChat={() => setActiveView('chat')}
            onOpenSidebar={isSidebarCollapsed ? () => setIsSidebarCollapsed(false) : undefined}
          />
        ) : (
          <ChatInterface
            session={currentSession}
            onSendMessage={handleSendMessage}
            userName={userName}
            onOpenSidebar={isSidebarCollapsed ? () => setIsSidebarCollapsed(false) : undefined}
          />
        )}
      </div>

      <IngestionModal
        isOpen={ingestionModalOpen}
        onClose={closeIngestionModal}
        status={ingestionStatus}
        stats={ingestionStats}
        onStartIngestion={handleIngestWithStrategy}
      />

      <DeleteVectorModal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
      />

      <JiraIngestModal
        isOpen={jiraModalOpen}
        onClose={() => setJiraModalOpen(false)}
      />
    </div>
  );
}

export default App;
