"""Document processing with incremental ingestion support."""
import os
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import settings
from database.session_db import session_db
import logging

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Process documents with incremental ingestion."""
    
    def __init__(self):
        """Initialize document processor."""
        from docling.document_converter import DocumentConverter
        self.converter = DocumentConverter()
        
        # Use RecursiveCharacterTextSplitter for better chunking of markdown
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            length_function=len,
            separators=["\n## ", "\n# ", "\n\n", "\n", ". ", " ", ""]
        )
    
    def calculate_file_hash(self, file_path: str) -> str:
        """
        Calculate SHA-256 hash of a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Hex digest of file hash
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def get_files_to_process(self) -> Tuple[List[str], List[str]]:
        """
        Get list of files that need processing (new or modified).
        
        Returns:
            Tuple of (files_to_process, skipped_files)
        """
        data_path = settings.get_absolute_path(settings.data_folder)
        
        if not os.path.exists(data_path):
            logger.warning(f"Data folder not found: {data_path}")
            return [], []
        
        # Supported file extensions (Docling handles many)
        supported_extensions = {'.pdf', '.txt', '.md', '.docx', '.pptx', '.html'}
        
        all_files = []
        for ext in supported_extensions:
            all_files.extend(Path(data_path).rglob(f'*{ext}'))
        
        files_to_process = []
        skipped_files = []
        
        for file_path in all_files:
            file_path_str = str(file_path)
            filename = file_path.name
            
            # Calculate current file hash
            current_hash = self.calculate_file_hash(file_path_str)
            
            # Check if file already ingested
            existing_doc = session_db.get_document_by_filename(filename)
            
            if existing_doc:
                # Check if file has been modified
                if existing_doc.file_hash == current_hash:
                    # File unchanged, skip
                    skipped_files.append(filename)
                    logger.info(f"Skipping unchanged file: {filename}")
                else:
                    # File modified, reprocess
                    files_to_process.append(file_path_str)
                    logger.info(f"File modified, will reprocess: {filename}")
            else:
                # New file, process
                files_to_process.append(file_path_str)
                logger.info(f"New file found: {filename}")
        
        return files_to_process, skipped_files
    
    def load_document(self, file_path: str) -> List:
        """
        Load a document using Docling for high-quality extraction.
        
        Args:
            file_path: Path to document
            
        Returns:
            List of LangChain Document objects (Markdown content)
        """
        from langchain_core.documents import Document
        try:
            logger.info(f"Converting {Path(file_path).name} using Docling...")
            result = self.converter.convert(file_path)
            markdown_content = result.document.export_to_markdown()
            
            # Create a single LangChain Document with the markdown content
            doc = Document(
                page_content=markdown_content,
                metadata={"source": file_path, "filename": Path(file_path).name}
            )
            
            return [doc]
            
        except Exception as e:
            logger.error(f"Docling error loading {file_path}: {str(e)}")
            return []
    
    def process_documents(self, file_paths: List[str], chunk_size: int = None, chunk_overlap: int = None) -> Dict:
        """
        Process documents: load, chunk, and prepare for embedding.
        
        Args:
            file_paths: List of file paths to process
            chunk_size: Optional chunk size override
            chunk_overlap: Optional chunk overlap override
            
        Returns:
            Dictionary with processed chunks and metadata
        """
        from tqdm import tqdm
        
        # Use provided values or defaults from settings
        c_size = chunk_size or settings.chunk_size
        c_overlap = chunk_overlap or settings.chunk_overlap
        
        # Create a temporary splitter if overrides are provided
        if chunk_size or chunk_overlap:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=c_size,
                chunk_overlap=c_overlap,
                length_function=len,
                separators=["\n\n", "\n", ". ", " ", ""]
            )
        else:
            splitter = self.text_splitter
        
        all_chunks = []
        all_metadatas = []
        file_chunk_counts = {}
        
        print(f"Starting processing of {len(file_paths)} files...")
        
        for file_path in tqdm(file_paths, desc="Processing Files", unit="file"):
            filename = Path(file_path).name
            
            # Load document
            documents = self.load_document(file_path)
            if not documents:
                continue
            
            # Split into chunks
            chunks = splitter.split_documents(documents)
            
            # Prepare metadata for each chunk
            for i, chunk in enumerate(chunks):
                # Extract page number if available
                page_num = chunk.metadata.get('page', 0)
                
                chunk_metadata = {
                    'filename': filename,
                    'file_path': file_path,
                    'chunk_index': i,
                    'page': page_num,
                    'source': file_path
                }
                
                all_chunks.append(chunk.page_content)
                all_metadatas.append(chunk_metadata)
            
            file_chunk_counts[filename] = len(chunks)
            logger.info(f"Processed {filename}: {len(chunks)} chunks")
        
        return {
            'chunks': all_chunks,
            'metadatas': all_metadatas,
            'file_chunk_counts': file_chunk_counts
        }
    
    def update_document_metadata(self, file_path: str, chunk_count: int) -> None:
        """
        Update document metadata in database.
        
        Args:
            file_path: Path to file
            chunk_count: Number of chunks created
        """
        filename = Path(file_path).name
        file_hash = self.calculate_file_hash(file_path)
        
        session_db.add_document_metadata(
            filename=filename,
            file_hash=file_hash,
            file_path=file_path,
            chunk_count=chunk_count
        )


# Global document processor instance
document_processor = DocumentProcessor()
