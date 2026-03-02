import React, { useState, useEffect } from 'react';
import api from '../services/api';
import './DeleteVectorModal.css';

/**
 * Vector store management modal.
 * Shows separate cards for JIRA and PDF collections with live counts
 * so users know exactly what they're deleting.
 */
function DeleteVectorModal({ isOpen, onClose }) {
    const [stats, setStats] = useState(null);
    const [loadingStats, setLoadingStats] = useState(false);

    // Active confirmation: null | 'pdf' | 'jira'
    const [confirming, setConfirming] = useState(null);
    const [confirmText, setConfirmText] = useState('');
    const [confirmError, setConfirmError] = useState('');
    const [deleting, setDeleting] = useState(false);
    const [deleted, setDeleted] = useState(null); // stores success message

    useEffect(() => {
        if (isOpen) {
            setConfirming(null);
            setConfirmText('');
            setConfirmError('');
            setDeleted(null);
            fetchStats();
        }
    }, [isOpen]);

    const fetchStats = async () => {
        setLoadingStats(true);
        try {
            const res = await api.get('/ingest/vector-stats');
            setStats(res.data);
        } catch {
            setStats(null);
        } finally {
            setLoadingStats(false);
        }
    };

    const startConfirm = (type) => {
        setConfirming(type);
        setConfirmText('');
        setConfirmError('');
        setDeleted(null);
    };

    const handleDelete = async () => {
        if (confirmText.toLowerCase() !== 'delete') {
            setConfirmError('Please type "delete" to confirm.');
            return;
        }
        setDeleting(true);
        try {
            const endpoint = confirming === 'jira'
                ? '/ingest/jira-vector-store'
                : '/ingest/vector-store';
            const res = await api.delete(endpoint);
            setDeleted(res.data.message);
            setConfirming(null);
            fetchStats(); // refresh counts
        } catch (e) {
            setConfirmError('Deletion failed. ' + (e.response?.data?.detail || e.message));
        } finally {
            setDeleting(false);
        }
    };

    if (!isOpen) return null;

    const jira = stats?.jira_collection;
    const pdf = stats?.pdf_collection;
    const bm25 = stats?.bm25_index;

    return (
        <div className="delete-modal-overlay" onClick={onClose}>
            <div className="delete-modal delete-modal-wide" onClick={e => e.stopPropagation()}>
                <div className="delete-modal-header">
                    <h3>🗄️ Manage Vector Stores</h3>
                    <button className="close-btn" onClick={onClose}>×</button>
                </div>

                <div className="delete-modal-content">
                    {deleted && (
                        <div className="delete-success-banner">
                            ✅ {deleted}
                        </div>
                    )}

                    {loadingStats ? (
                        <div className="processing-state"><div className="spinner"></div><p>Loading stats…</p></div>
                    ) : (
                        <div className="store-cards">
                            {/* ── JIRA Store Card ── */}
                            <div className="store-card store-card-jira">
                                <div className="store-card-icon">🎫</div>
                                <div className="store-card-info">
                                    <h4>JIRA Tickets</h4>
                                    <p className="store-collection-name">Collection: <code>{jira?.name || 'jira_tickets'}</code></p>
                                    <p className="store-count">
                                        <strong>{jira?.count ?? '—'}</strong> vectors
                                        {bm25 ? <span className="store-sublabel"> + {bm25.count} BM25 tickets in OpenSearch</span> : null}
                                    </p>
                                    <p className="store-desc">{jira?.description}</p>
                                </div>
                                <button
                                    className="store-delete-btn"
                                    onClick={() => startConfirm('jira')}
                                    disabled={!jira || jira.count === 0}
                                    title={jira?.count === 0 ? 'Collection is already empty' : 'Delete JIRA ticket vectors'}
                                >
                                    🗑️ Delete
                                </button>
                            </div>

                            {/* ── PDF Store Card ── */}
                            <div className="store-card store-card-pdf">
                                <div className="store-card-icon">📄</div>
                                <div className="store-card-info">
                                    <h4>PDF / Documents</h4>
                                    <p className="store-collection-name">Collection: <code>{pdf?.name || 'document_chunks'}</code></p>
                                    <p className="store-count"><strong>{pdf?.count ?? '—'}</strong> vectors</p>
                                    <p className="store-desc">{pdf?.description}</p>
                                </div>
                                <button
                                    className="store-delete-btn"
                                    onClick={() => startConfirm('pdf')}
                                    disabled={!pdf || pdf.count === 0}
                                    title={pdf?.count === 0 ? 'Collection is already empty' : 'Delete PDF document vectors'}
                                >
                                    🗑️ Delete
                                </button>
                            </div>
                        </div>
                    )}

                    {/* ── Inline confirmation panel ── */}
                    {confirming && !deleting && (
                        <div className="delete-confirm-panel">
                            <div className="warning-icon">⚠️</div>
                            <h4>Delete {confirming === 'jira' ? 'JIRA ticket' : 'PDF document'} vectors?</h4>
                            <p className="warning-text">
                                This will permanently remove all{' '}
                                <strong>{confirming === 'jira' ? (jira?.count ?? 0) : (pdf?.count ?? 0)}</strong>{' '}
                                vectors from the <code>{confirming === 'jira' ? jira?.name : pdf?.name}</code> collection.
                                {confirming === 'jira' && ' The OpenSearch BM25 index will also be cleared on next re-index.'}
                                {' '}This cannot be undone.
                            </p>
                            <label>Type <strong>delete</strong> to confirm:</label>
                            <input
                                className={`confirm-input ${confirmError ? 'input-error' : ''}`}
                                type="text"
                                autoFocus
                                value={confirmText}
                                onChange={e => { setConfirmText(e.target.value); setConfirmError(''); }}
                                onKeyDown={e => e.key === 'Enter' && handleDelete()}
                            />
                            {confirmError && <span className="error-message">{confirmError}</span>}
                            <div className="delete-actions">
                                <button className="cancel-btn" onClick={() => setConfirming(null)}>Cancel</button>
                                <button
                                    className="confirm-delete-btn"
                                    onClick={handleDelete}
                                    disabled={confirmText.toLowerCase() !== 'delete'}
                                >
                                    Yes, delete {confirming === 'jira' ? 'JIRA' : 'PDF'} store
                                </button>
                            </div>
                        </div>
                    )}

                    {deleting && (
                        <div className="processing-state">
                            <div className="spinner danger-spinner"></div>
                            <p>Deleting…</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default DeleteVectorModal;
