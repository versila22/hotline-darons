"""PDF Parser for Knowledge Base

Simple PDF text extraction using PyPDF2.
Extracts text from PDF files for RAG indexing.
"""

import logging
from pathlib import Path
from typing import List, Dict
try:
    from PyPDF2 import PdfReader
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    logging.warning("PyPDF2 not installed. PDF support disabled.")

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: Path) -> List[Dict]:
    """Extract text from a PDF file, page by page.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        List of dicts with "text" and "source" keys
    """
    if not PDF_SUPPORT:
        logger.error("PyPDF2 not available - cannot parse PDFs")
        return []
    
    chunks = []
    
    try:
        reader = PdfReader(str(pdf_path))
        logger.info(f"📖 Parsing {pdf_path.name}: {len(reader.pages)} pages")
        
        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            if text and text.strip():
                chunks.append({
                    "text": text.strip(),
                    "source": f"{pdf_path.name} (page {page_num})"
                })
        
        logger.info(f"✅ Extracted {len(chunks)} chunks from {pdf_path.name}")
        
    except Exception as e:
        logger.error(f"❌ Failed to parse {pdf_path.name}: {e}")
    
    return chunks


def parse_pdf_files(knowledge_dir: Path) -> List[Dict]:
    """Parse all PDF files in the knowledge directory.
    
    Args:
        knowledge_dir: Path to knowledge directory
        
    Returns:
        List of text chunks from all PDFs
    """
    if not PDF_SUPPORT:
        return []
    
    pdf_files = list(knowledge_dir.glob("*.pdf"))
    
    if not pdf_files:
        logger.debug("No PDF files found in knowledge directory")
        return []
    
    logger.info(f"📚 Found {len(pdf_files)} PDF file(s)")
    
    all_chunks = []
    for pdf_path in pdf_files:
        chunks = extract_text_from_pdf(pdf_path)
        all_chunks.extend(chunks)
    
    return all_chunks


if __name__ == "__main__":
    # Test PDF parsing
    import sys
    
    print("🧪 Testing PDF parser...")
    
    if not PDF_SUPPORT:
        print("❌ PyPDF2 not installed. Install with: pip install PyPDF2")
        sys.exit(1)
    
    test_dir = Path("knowledge")
    if not test_dir.exists():
        print("❌ knowledge/ directory not found")
        sys.exit(1)
    
    chunks = parse_pdf_files(test_dir)
    
    if chunks:
        print(f"\n✅ Successfully extracted {len(chunks)} chunks:")
        for i, chunk in enumerate(chunks[:3], 1):
            print(f"\n{i}. {chunk['source']}")
            print(f"   {chunk['text'][:100]}...")
    else:
        print("⚠️ No PDF files found or extraction failed")
