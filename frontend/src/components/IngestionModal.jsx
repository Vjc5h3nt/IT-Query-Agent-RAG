import React from 'react';
import './IngestionModal.css';

function IngestionModal({ isOpen, onClose, status, step, stats, onStartIngestion }) {
    if (!isOpen) return null;

    return (
        <div className="ingestion-modal-overlay">
            <div className="ingestion-modal">
                <div className="ingestion-header">
                    <h3>Document Ingestion</h3>
                    {!status && <button className="close-btn" onClick={onClose}>&times;</button>}
                </div>

                <div className="ingestion-content">
                    {!status ? (
                        <div className="selection-state">
                            <p className="selection-info">Select an ingestion strategy for your documents:</p>

                            <div className="strategy-options">
                                <div className="strategy-card" onClick={() => onStartIngestion('normal')}>
                                    <div className="strategy-icon">📘</div>
                                    <div className="strategy-title">Standard RAG</div>
                                    <ul className="strategy-features">
                                        <li>Chunk Size: 1000</li>
                                        <li>Overlap: 200</li>
                                        <li>Memory: 5 Messages</li>
                                    </ul>
                                    <button className="select-btn">Select Standard</button>
                                </div>

                                <div className="strategy-card premium" onClick={() => onStartIngestion('rerank')}>
                                    <div className="strategy-icon">⚡</div>
                                    <div className="strategy-title">Performance (Cross-Encoder)</div>
                                    <ul className="strategy-features">
                                        <li>Chunk Size: 400 (Denser)</li>
                                        <li>Top-K Stage 1: 40</li>
                                        <li>Memory: 12 Messages</li>
                                    </ul>
                                    <div className="premium-tag">Recommended for Accuracy</div>
                                    <button className="select-btn">Select Performance</button>
                                </div>
                            </div>
                        </div>
                    ) : status === 'processing' ? (
                        <div className="processing-state">
                            <div className="spinner"></div>
                            <p>Processing documents...</p>
                            <div className="step-indicator">
                                Check terminal for progress bar
                            </div>
                        </div>
                    ) : status === 'complete' ? (
                        <div className="complete-state">
                            <div className="success-icon">✅</div>
                            <h4>Ingestion Complete!</h4>

                            <div className="stats-grid">
                                <div className="stat-item">
                                    <span className="stat-label">Total Files</span>
                                    <span className="stat-value">{stats?.total_files || 0}</span>
                                </div>
                                <div className="stat-item">
                                    <span className="stat-label">Processed</span>
                                    <span className="stat-value new">{stats?.new_files_processed || 0}</span>
                                </div>
                                <div className="stat-item">
                                    <span className="stat-label">Skipped</span>
                                    <span className="stat-value skipped">{stats?.skipped_files || 0}</span>
                                </div>
                                <div className="stat-item">
                                    <span className="stat-label">Chunks</span>
                                    <span className="stat-value">{stats?.total_chunks_created || 0}</span>
                                </div>
                            </div>

                            <div className="file-lists">
                                {stats?.processed_files?.length > 0 && (
                                    <div className="file-list">
                                        <h5>Processed:</h5>
                                        <ul>
                                            {stats.processed_files.map((f, i) => <li key={i}>{f}</li>)}
                                        </ul>
                                    </div>
                                )}
                            </div>

                            <button className="done-btn" onClick={onClose}>Done</button>
                        </div>
                    ) : status === 'error' ? (
                        <div className="error-state">
                            <div className="error-icon">❌</div>
                            <h4>Ingestion Failed</h4>
                            <p>{stats?.error || 'Unknown error occurred'}</p>
                            <button className="done-btn" onClick={onClose}>Close</button>
                        </div>
                    ) : null}
                </div>
            </div>
        </div>
    );
}

export default IngestionModal;
