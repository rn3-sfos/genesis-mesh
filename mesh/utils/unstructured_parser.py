from typing import List, Optional
from functools import lru_cache
from pathlib import Path
from unstructured.partition.auto import partition
from unstructured.documents.elements import Element
from langchain.schema import Document
from langchain_community.document_transformers import MarkdownifyTransformer
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)


class UnstructuredParser:
    def __init__(self, max_workers: int = 4) -> None:
        """Initialize parser with configurable thread pool and cache size.

        Args:
            max_workers: Maximum number of worker threads
            cache_size: Size of LRU cache for document processing
        """
        self.md_transformer = MarkdownifyTransformer()
        self.max_workers = max_workers

    def __document_to_md(self, document_content: str) -> str:
        """Convert document to markdown with caching for repeated content."""
        document = Document(page_content=document_content)
        md_contents = self.md_transformer.transform_documents([document])
        return "\n".join(
            md_content.page_content
            for md_content in md_contents
            if md_content.page_content.strip()
        )

    def __process_element(self, element: Element) -> str:
        """Process individual elements with error handling."""
        try:
            if element.metadata.text_as_html:
                return element.metadata.text_as_html
            return f"<div>{element.text}</div>"
        except AttributeError as e:
            logger.warning(f"Error processing element: {e}")
            return ""

    def __parse_elements(self, elements: List[Element]) -> Document:
        """Parse elements using parallel processing for large documents."""
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            content = list(executor.map(self.__process_element, elements))
        return Document(page_content="\n".join(filter(None, content)))

    @lru_cache(maxsize=128)
    def parse_document(self, file_path: str, chunk_size: Optional[int] = None) -> str:
        """Parse document with improved error handling and optional chunking.

        Args:
            file_path: Path to document
            chunk_size: Optional size for processing document in chunks

        Returns:
            Markdown formatted string
        """
        try:
            file_path = Path(file_path).resolve()
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            elements = partition(
                filename=str(file_path),
                strategy="hi_res",
                skip_infer_table_types=[],
                pdf_infer_table_structure=True,
            )

            if chunk_size and len(elements) > chunk_size:
                # Process large documents in chunks
                result = []
                for i in range(0, len(elements), chunk_size):
                    chunk = elements[i : i + chunk_size]
                    html_content = self.__parse_elements(chunk)
                    result.append(self.__document_to_md(html_content.page_content))
                return "\n".join(result)

            html_content = self.__parse_elements(elements)
            return self.__document_to_md(html_content.page_content)

        except Exception as e:
            logger.error(f"Error parsing document {file_path}: {e}")
            raise
