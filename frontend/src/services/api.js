/**
 * API client for backend communication
 */
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Session endpoints
export const createSession = async (name = null) => {
    const response = await api.post('/sessions', { name });
    return response.data;
};

export const getSessions = async () => {
    const response = await api.get('/sessions');
    return response.data;
};

export const getSession = async (sessionId) => {
    const response = await api.get(`/sessions/${sessionId}`);
    return response.data;
};

export const deleteSession = async (sessionId) => {
    const response = await api.delete(`/sessions/${sessionId}`);
    return response.data;
};

export const updateSession = async (sessionId, name) => {
    const response = await api.patch(`/sessions/${sessionId}`, { name });
    return response.data;
};

export const deleteAllSessions = async () => {
    const response = await api.delete('/sessions');
    return response.data;
};

// Chat endpoints
export const sendMessage = async (sessionId, message, useKnowledgeBase = true, useReranking = false) => {
    const response = await api.post('/chat', {
        session_id: sessionId,
        message: message,
        use_knowledge_base: useKnowledgeBase,
        use_reranking: useReranking
    });
    return response.data;
};

// Ingestion endpoints
export const ingestDocuments = async (settings = {}) => {
    const response = await api.post('/ingest', settings);
    return response.data;
};

export const getIngestionStatus = async () => {
    const response = await api.get('/ingest/status');
    return response.data;
};

export default api;
