import React from 'react';
import './IngestionModal.css';

function IngestionModal({ isOpen, onClose, status, step, stats, onStartIngestion }) {
    if (!isOpen) return null;

    const isProcessing = status === 'processing';

    // Steps mapping for the pipeline UI
    const getStepClass = (stepName) => {
        const flow = ['idle', 'processing', 'complete'];
        const currentIdx = flow.indexOf(status || 'idle');
        const myIdx = flow.indexOf(stepName);

        if (status === 'error') {
            if (myIdx < 1) return 'step-completed';
            if (myIdx === 1) return 'step-active error'; // Could add error style
            return 'step-pending';
        }

        if (myIdx < currentIdx) return 'step-completed';
        if (myIdx === currentIdx) return 'step-active';
        return 'step-pending';
    };

    return (
        <div className="ingestion-modal-overlay" onClick={!isProcessing ? onClose : undefined}>
            <div className="ingestion-modal" onClick={e => e.stopPropagation()}>
                <div className="ingestion-header">
                    <div className="ingestion-title-content">
                        <span className="ingestion-title-icon">📚</span>
                        <h3>Document Ingestion Pipeline</h3>
                    </div>
                    {!isProcessing && (
                        <button className="close-btn" onClick={onClose}>&times;</button>
                    )}
                </div>

                {/* STEPPER UI - Matching JIRA UX */}
                <div className="ingestion-stepper">
                    <div className={`ingestion-step ${getStepClass('idle')}`}>1. Prepare</div>
                    <div className="ingestion-step-separator"></div>
                    <div className={`ingestion-step ${getStepClass('processing')}`}>2. Extract & Index</div>
                    <div className="ingestion-step-separator"></div>
                    <div className={`ingestion-step ${getStepClass('complete')}`}>3. Complete</div>
                </div>

                <div className="ingestion-content">
                    {/* PHASE: IDLE (SELECTION) */}
                    {!status && (
                        <div className="selection-state">
                            <p className="selection-info">
                                Documents in the <code>/data</code> folder will be processed using the High-Performance engine.
                            </p>

                            <div className="strategy-card premium" onClick={() => onStartIngestion()}>
                                <div className="strategy-title">Performance (Cross-Encoder)</div>
                                <ul className="strategy-features">
                                    <li>• Engine: Docling Markdown Extraction</li>
                                    <li>• Retrieval: Two-Stage Semantic Reranking</li>
                                    <li>• Vectors: Amazon Titan v1</li>
                                </ul>
                                <button className="select-btn">Start High-Performance Ingestion</button>
                            </div>
                        </div>
                    )}

                    {/* PHASE: PROCESSING */}
                    {status === 'processing' && (
                        <div className="processing-state">
                            <div className="spinner"></div>
                            <div className="processing-labels">
                                <p className="selection-info">Running Docling extraction and vector indexing...</p>
                                <div className="step-indicator">
                                    Check terminal for real-time progress bar
                                </div>
                            </div>
                        </div>
                    )}

                    {/* PHASE: COMPLETE */}
                    {status === 'complete' && (
                        <div className="complete-state">
                            <div className="success-icon">✅</div>
                            <h4>Ingestion Success</h4>

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
                                {stats?.processed_files?.length > 0 ? (
                                    <div className="file-list">
                                        <strong>Newly Indexed:</strong>
                                        <ul style={{ listStyle: 'none', padding: 0, marginTop: '8px' }}>
                                            {stats.processed_files.map((f, i) => (
                                                <li key={i} style={{ marginBottom: '4px' }}>• {f}</li>
                                            ))}
                                        </ul>
                                    </div>
                                ) : (
                                    <p style={{ color: 'var(--text-muted)' }}>No new files were modified or added.</p>
                                )}
                            </div>

                            <button className="done-btn" onClick={onClose}>Done</button>
                        </div>
                    )}

                    {/* PHASE: ERROR */}
                    {status === 'error' && (
                        <div className="error-state">
                            <div className="error-icon">❌</div>
                            <h4>Ingestion Error</h4>
                            <p>{stats?.error || 'A technical error occurred during processing.'}</p>
                            <button className="retry-btn" onClick={onClose}>Close</button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default IngestionModal;
