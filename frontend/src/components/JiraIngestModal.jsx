import React, { useState, useRef, useCallback } from 'react';
import './JiraIngestModal.css';

const API_BASE = import.meta.env.VITE_API_URL || '';

function JiraIngestModal({ isOpen, onClose }) {
    // phase: idle | uploading | extracting | extracted | cleaning | cleaned | indexing | complete | error
    const [phase, setPhase] = useState('idle');
    const [dragOver, setDragOver] = useState(false);
    const [selectedFile, setSelectedFile] = useState(null);
    const [batchSize, setBatchSize] = useState(100);
    const [stats, setStats] = useState(null);
    const [errorMsg, setErrorMsg] = useState('');
    const [sessionId, setSessionId] = useState(null);
    const [previewData, setPreviewData] = useState([]);

    const fileInputRef = useRef();
    const readerRef = useRef(null);

    const reset = () => {
        setPhase('idle');
        setSelectedFile(null);
        setStats(null);
        setErrorMsg('');
        setSessionId(null);
        setPreviewData([]);
        setDragOver(false);
        if (readerRef.current) {
            readerRef.current.cancel?.();
        }
    };

    const handleClose = () => {
        reset();
        onClose();
    };

    const handleDrop = useCallback((e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file && file.name.endsWith('.xml')) {
            setSelectedFile(file);
        } else {
            setErrorMsg('Please drop a valid JIRA .xml export file.');
        }
    }, []);

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (file) setSelectedFile(file);
    };

    const handleUpload = async () => {
        if (!selectedFile) return;
        setPhase('uploading');
        setErrorMsg('');

        const formData = new FormData();
        formData.append('file', selectedFile);

        try {
            const response = await fetch(`${API_BASE}/ingest/jira/upload`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
                throw new Error(err.detail || 'Upload failed');
            }

            const data = await response.json();
            setSessionId(data.session_id);
            // Auto-proceed to extraction
            handleExtract(data.session_id);

        } catch (e) {
            setPhase('error');
            setErrorMsg(e.message || 'Something went wrong during upload');
        }
    };

    const handleExtract = async (sid) => {
        setPhase('extracting');
        try {
            const response = await fetch(`${API_BASE}/ingest/jira/extract/${sid}`, { method: 'POST' });
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Extraction failed' }));
                throw new Error(err.detail || 'Extraction failed');
            }
            const data = await response.json();
            setPreviewData(data.preview);
            setPhase('extracted');
        } catch (e) {
            setPhase('error');
            setErrorMsg(e.message || 'Something went wrong during extraction');
        }
    };

    const handleClean = async () => {
        setPhase('cleaning');
        try {
            const response = await fetch(`${API_BASE}/ingest/jira/clean/${sessionId}`, { method: 'POST' });
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Cleaning failed' }));
                throw new Error(err.detail || 'Cleaning failed');
            }
            const data = await response.json();
            setPreviewData(data.preview);
            setPhase('cleaned');
        } catch (e) {
            setPhase('error');
            setErrorMsg(e.message || 'Something went wrong during cleaning');
        }
    };

    const handleIndex = async () => {
        setPhase('indexing');
        setStats(null);

        try {
            const response = await fetch(`${API_BASE}/ingest/jira/index/${sessionId}?batch_size=${batchSize}`, { method: 'POST' });
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Indexing failed' }));
                throw new Error(err.detail || 'Indexing failed');
            }

            const reader = response.body.getReader();
            readerRef.current = reader;
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() ?? '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            setStats({ ...data });
                            if (data.status === 'complete') setPhase('complete');
                            if (data.status === 'error') {
                                setPhase('error');
                                setErrorMsg(data.error || 'Unknown error during indexing');
                            }
                        } catch { /* ignore non-JSON SSE lines */ }
                    }
                }
            }
        } catch (e) {
            setPhase('error');
            setErrorMsg(e.message || 'Something went wrong during indexing');
        }
    };

    const downloadFile = (phaseParam) => {
        window.open(`${API_BASE}/ingest/jira/download/${sessionId}/${phaseParam}`, '_blank');
    };

    if (!isOpen) return null;

    const isProcessing = ['uploading', 'extracting', 'cleaning', 'indexing'].includes(phase);

    // Steps mapping
    const getStepClass = (stepPhase) => {
        const flow = ['idle', 'extracted', 'cleaned', 'indexing', 'complete'];
        let currentIdx = flow.indexOf(phase);
        if (phase === 'uploading' || phase === 'extracting') currentIdx = 1;
        if (phase === 'cleaning') currentIdx = 2;

        const myIdx = flow.indexOf(stepPhase);
        if (myIdx < currentIdx) return 'step-completed';
        if (myIdx === currentIdx) return 'step-active';
        return 'step-pending';
    };

    return (
        <div className="jira-modal-overlay" onClick={!isProcessing ? handleClose : undefined}>
            <div className="jira-modal" onClick={e => e.stopPropagation()}>
                <div className="jira-modal-header">
                    <div className="jira-modal-title">
                        <span className="jira-title-icon">🗂️</span>
                        <h3>Interactive JIRA Pipeline</h3>
                    </div>
                    {!isProcessing && (
                        <button className="jira-close-btn" onClick={handleClose}>&times;</button>
                    )}
                </div>

                {/* STEPPER UI */}
                <div className="jira-stepper">
                    <div className={`jira-step ${getStepClass('idle')}`}>1. Upload</div>
                    <div className="jira-step-separator"></div>
                    <div className={`jira-step ${getStepClass('extracted')}`}>2. Extract</div>
                    <div className="jira-step-separator"></div>
                    <div className={`jira-step ${getStepClass('cleaned')}`}>3. Clean</div>
                    <div className="jira-step-separator"></div>
                    <div className={`jira-step ${getStepClass('indexing')}`}>4. Index</div>
                </div>

                <div className="jira-modal-body">

                    {/* PHASE: IDLE (UPLOAD) */}
                    {phase === 'idle' && (
                        <div className="jira-step-content">
                            <p className="jira-subtitle">Upload your XML. We'll extract the data first before letting you review it.</p>
                            <div
                                className={`jira-dropzone ${dragOver ? 'drag-over' : ''} ${selectedFile ? 'file-selected' : ''}`}
                                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                                onDragLeave={() => setDragOver(false)}
                                onDrop={handleDrop}
                                onClick={() => fileInputRef.current?.click()}
                            >
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept=".xml"
                                    style={{ display: 'none' }}
                                    onChange={handleFileChange}
                                />
                                {selectedFile ? (
                                    <div className="jira-file-selected">
                                        <span className="file-icon">📄</span>
                                        <div className="file-info">
                                            <span className="file-name">{selectedFile.name}</span>
                                            <span className="file-size">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</span>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="jira-dropzone-prompt">
                                        <span className="drop-icon">📂</span>
                                        <p>Drag & drop JIRA XML here</p>
                                    </div>
                                )}
                            </div>
                            {errorMsg && <p className="jira-error-text">{errorMsg}</p>}
                            <div className="jira-modal-footer">
                                <button className="jira-primary-btn" disabled={!selectedFile} onClick={handleUpload}>
                                    Upload & Extract Data
                                </button>
                            </div>
                        </div>
                    )}

                    {/* PHASE: LOADING (Shared for Uploading/Extracting/Cleaning) */}
                    {(phase === 'uploading' || phase === 'extracting' || phase === 'cleaning') && (
                        <div className="jira-loading-state">
                            <div className="jira-spinner"></div>
                            <p className="jira-running-label">
                                {phase === 'uploading' && 'Uploading XML to server...'}
                                {phase === 'extracting' && 'Extracting ticket fields...'}
                                {phase === 'cleaning' && 'Aggressively cleaning HTML and signatures...'}
                            </p>
                        </div>
                    )}

                    {/* PHASE: EXTRACTED PREVIEW */}
                    {phase === 'extracted' && (
                        <div className="jira-step-content">
                            <h4>Step 2: Raw Extraction Complete</h4>
                            <p className="jira-desc">The structural fields have been extracted, but notice the raw HTML tags and dirty signatures in the descriptions.</p>

                            <div className="jira-preview-box">
                                {previewData.map(ticket => (
                                    <div key={ticket.ticket_id} className="jira-preview-ticket">
                                        <strong>{ticket.ticket_id}</strong> - {ticket.summary.substring(0, 100)}...
                                        <div className="preview-code">
                                            {ticket.description.substring(0, 250)}...
                                        </div>
                                    </div>
                                ))}
                            </div>

                            <div className="jira-modal-footer dual">
                                <button className="jira-secondary-btn" onClick={() => downloadFile('extracted')}>
                                    📥 Download extracted.jsonl
                                </button>
                                <button className="jira-primary-btn" onClick={handleClean}>
                                    Next: Clean HTML
                                </button>
                            </div>
                        </div>
                    )}

                    {/* PHASE: CLEANED PREVIEW */}
                    {phase === 'cleaned' && (
                        <div className="jira-step-content">
                            <h4>Step 3: Cleaning Complete ✅</h4>
                            <p className="jira-desc">HTML, email signatures, and attachments have been stripped. The data is ready for semantic embedding.</p>

                            <div className="jira-preview-box">
                                {previewData.map(ticket => (
                                    <div key={ticket.ticket_id} className="jira-preview-ticket">
                                        <strong>{ticket.ticket_id}</strong> - {ticket.summary.substring(0, 100)}...
                                        <div className="preview-code clean">
                                            {ticket.description.substring(0, 250)}...
                                        </div>
                                    </div>
                                ))}
                            </div>

                            {/* ── Batch size card ── */}
                            <div className="jira-batch-card">
                                <div className="jira-batch-header">
                                    <div>
                                        <span className="jira-batch-title">⚙️ Embedding Batch Size</span>
                                        <span className="jira-batch-hint">Higher = faster but uses more memory</span>
                                    </div>
                                    <span className="jira-batch-badge">{batchSize}</span>
                                </div>
                                <input
                                    type="range"
                                    min={10}
                                    max={500}
                                    step={10}
                                    value={batchSize}
                                    onChange={e => setBatchSize(Number(e.target.value))}
                                    className="jira-range jira-range-full"
                                />
                                <div className="jira-batch-ticks">
                                    <span>10</span>
                                    <span>Recommended: 100</span>
                                    <span>500</span>
                                </div>
                            </div>

                            {/* ── Footer actions ── */}
                            <div className="jira-step4-actions">
                                <button className="jira-ghost-btn" onClick={() => downloadFile('cleaned')}>
                                    📥 Download cleaned.jsonl
                                </button>
                                <button className="jira-index-btn" onClick={handleIndex}>
                                    <span className="jira-index-btn-icon">⚡</span>
                                    Embed &amp; Index into Vector Store
                                </button>
                            </div>
                        </div>
                    )}

                    {/* PHASE: INDEXING (SSE) */}
                    {phase === 'indexing' && (
                        <div className="jira-running-state">
                            <div className="jira-spinner"></div>
                            <p className="jira-running-label">Indexing into Chroma & OpenSearch...</p>

                            <div className="jira-live-stats">
                                <div className="jira-stat-box"><span className="jira-stat-value">{stats?.tickets_parsed ?? 0}</span><span className="jira-stat-label">Parsed</span></div>
                                <div className="jira-stat-box highlight"><span className="jira-stat-value">{stats?.vectors_created ?? 0}</span><span className="jira-stat-label">Vectors</span></div>
                                <div className="jira-stat-box"><span className="jira-stat-value">{stats?.deduplicated ?? 0}</span><span className="jira-stat-label">Deduped</span></div>
                            </div>
                        </div>
                    )}

                    {/* PHASE: COMPLETE */}
                    {phase === 'complete' && (
                        <div className="jira-complete-state">
                            <div className="jira-complete-icon">✅</div>
                            <h4>Ingestion Complete!</h4>
                            <div className="jira-final-stats">
                                <div className="jira-stat-box highlight"><span className="jira-stat-value">{stats?.vectors_created ?? 0}</span><span className="jira-stat-label">Vectors</span></div>
                            </div>
                            <p className="jira-chroma-total">Total vectors in DB: <strong>{stats?.total_chroma_count ?? 0}</strong></p>
                            <button className="jira-done-btn" onClick={handleClose}>Done</button>
                        </div>
                    )}

                    {/* ERROR */}
                    {phase === 'error' && (
                        <div className="jira-error-state">
                            <div className="jira-error-icon">❌</div>
                            <h4>Error</h4>
                            <p className="jira-error-detail">{errorMsg}</p>
                            <button className="jira-retry-btn" onClick={reset}>Start Over</button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default JiraIngestModal;
