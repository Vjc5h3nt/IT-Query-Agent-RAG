/**
 * Main App component
 */
import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import IngestionModal from './components/IngestionModal';
import * as api from './services/api';
import './App.css';

function App() {
  const [sessions, setSessions] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [loading, setLoading] = useState(true);

  // Ingestion state
  const [ingestionModalOpen, setIngestionModalOpen] = useState(false);
  const [ingestionStatus, setIngestionStatus] = useState(null); // 'processing', 'complete', 'error'
  const [ingestionStats, setIngestionStats] = useState(null);

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

  // Load sessions on mount
  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    try {
      const data = await api.getSessions();
      setSessions(data);
      setLoading(false);
    } catch (error) {
      console.error('Error loading sessions:', error);
      setLoading(false);
    }
  };

  const handleNewSession = async () => {
    try {
      const newSession = await api.createSession();
      setSessions((prev) => [newSession, ...prev]);

      // Load full session details
      const sessionDetail = await api.getSession(newSession.id);
      setCurrentSession(sessionDetail);
    } catch (error) {
      console.error('Error creating session:', error);
      alert('Failed to create session');
    }
  };

  const handleSelectSession = async (sessionId) => {
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

  // Knowledge Base state
  const [useKnowledgeBase, setUseKnowledgeBase] = useState(true);
  const [useReranking, setUseReranking] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  const handleSendMessage = async (message) => {
    if (!currentSession) return;

    const response = await api.sendMessage(currentSession.id, message, useKnowledgeBase, useReranking);

    // Reload sessions to update "updated_at"
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

  const handleOpenIngestModal = () => {
    setIngestionModalOpen(true);
    setIngestionStatus(null); // 'null' shows the selection UI
    setIngestionStats(null);
  };

  const handleIngestWithStrategy = async (strategy) => {
    setIngestionStatus('processing');

    let settings = {};
    if (strategy === 'normal') {
      settings = {
        chunk_size: 1000,
        chunk_overlap: 200,
        top_k_stage1: 5,
        rerank_top_k: 5,
        max_memory_messages: 5
      };
    } else if (strategy === 'rerank') {
      settings = {
        chunk_size: 512,
        chunk_overlap: 100,
        top_k_stage1: 50,
        rerank_top_k: 5,
        max_memory_messages: 5
      };
      // Also enable reranking in the UI automatically if they choose this
      setUseReranking(true);
    }

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
    if (ingestionStatus === 'processing') return; // Prevent closing while processing
    setIngestionModalOpen(false);
    setIngestionStatus(null);
    setIngestionStats(null);
  };

  // Filter sessions based on search query
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
        onIngest={handleOpenIngestModal}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
        theme={theme}
        onToggleTheme={toggleTheme}
        userName={userName}
        onUpdateUserName={setUserName}
      />
      <div className="main-content">
        <ChatInterface
          session={currentSession}
          onSendMessage={handleSendMessage}
          useKnowledgeBase={useKnowledgeBase}
          onToggleKnowledgeBase={() => setUseKnowledgeBase(!useKnowledgeBase)}
          useReranking={useReranking}
          onToggleReranking={() => setUseReranking(!useReranking)}
          userName={userName}
        />
      </div>

      <IngestionModal
        isOpen={ingestionModalOpen}
        onClose={closeIngestionModal}
        status={ingestionStatus}
        stats={ingestionStats}
        onStartIngestion={handleIngestWithStrategy}
      />
    </div>
  );
}

export default App;
