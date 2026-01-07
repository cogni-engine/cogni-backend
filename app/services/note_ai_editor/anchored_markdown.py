"""Anchored Markdown Generator - Convert annotated markdown to AI-friendly format"""
import re
import logging
from typing import List, Tuple, Optional

from .id_mapper import BlockIdMapper

logger = logging.getLogger(__name__)


def extract_block_ids_from_annotated_markdown(annotated_markdown: str) -> List[str]:
    """
    Extract all block IDs from annotated markdown in document order.
    
    Args:
        annotated_markdown: Markdown with block ID comments
        
    Returns:
        List of block IDs in the order they appear
    """
    # Pattern to match block ID comments
    # Examples: 
    #   <!-- paragraph id="blk-123" -->
    #   <!-- heading id="blk-456" level=1 -->
    #   <!-- heading level=1 id="blk-789" -->
    # The pattern matches id="..." anywhere in the comment, with any attributes before or after
    block_id_pattern = re.compile(r'<!--[^>]*\sid="([^"]+)"[^>]*-->')
    
    block_ids = []
    for match in block_id_pattern.finditer(annotated_markdown):
        block_id = match.group(1)
        block_ids.append(block_id)
    
    logger.info(f"Extracted {len(block_ids)} block IDs from annotated markdown")
    return block_ids


def generate_ai_friendly_markdown(
    annotated_markdown: str,
    id_mapper: BlockIdMapper
) -> str:
    """
    Convert annotated markdown with complex IDs to AI-friendly format with simple IDs.
    
    Input format:
        <!-- paragraph id="blk-a1b2c3d4" -->
        Content here
        
    Output format:
        <!-- id="1" -->
        Content here
    
    Args:
        annotated_markdown: Markdown with complex block ID comments
        id_mapper: Mapper to convert complex IDs to simple IDs
        
    Returns:
        AI-friendly markdown with simple sequential IDs
    """
    # Pattern to match block ID comments with any attributes before or after the id
    # Matches: <!-- anything id="blk-xxx" anything -->
    block_id_pattern = re.compile(r'<!--[^>]*\sid="([^"]+)"[^>]*-->')
    
    def replace_id(match: re.Match) -> str:
        """Replace entire comment with simple ID comment"""
        complex_id = match.group(1)
        simple_id = id_mapper.to_simple_id(complex_id)
        
        if simple_id:
            # Replace entire comment with simple format
            return f'<!-- id="{simple_id}" -->'
        else:
            # If ID not found in mapper, keep original (shouldn't happen)
            logger.warning(f"Could not map complex ID {complex_id} to simple ID")
            return match.group(0)
    
    # Replace all complex IDs with simple IDs
    ai_friendly = block_id_pattern.sub(replace_id, annotated_markdown)
    
    logger.info(f"Generated AI-friendly markdown (length: {len(ai_friendly)} chars)")
    logger.debug(f"AI-friendly markdown preview:\n{ai_friendly[:500]}...")
    
    return ai_friendly


def create_id_mapper_from_annotated_markdown(annotated_markdown: str) -> BlockIdMapper:
    """
    Create an ID mapper from annotated markdown.
    
    Convenience function that extracts block IDs and creates a mapper in one step.
    
    Args:
        annotated_markdown: Markdown with block ID comments
        
    Returns:
        BlockIdMapper instance
    """
    block_ids = extract_block_ids_from_annotated_markdown(annotated_markdown)
    return BlockIdMapper(block_ids)


def extract_blocks_from_anchored_markdown(anchored_markdown: str) -> List[Tuple[str, str]]:
    """
    Extract blocks from anchored markdown output (e.g., from AI).
    
    Splits the markdown into (id, content) tuples based on anchor comments.
    
    Args:
        anchored_markdown: Markdown with simple ID anchors like <!-- id="1" -->
        
    Returns:
        List of (block_id, content) tuples
    """
    blocks: List[Tuple[str, str]] = []
    
    # Pattern to match ID anchors
    anchor_pattern = re.compile(r'<!--\s*id="([^"]+)"\s*-->')
    
    # Split by anchors
    parts = anchor_pattern.split(anchored_markdown)
    
    # parts will be: [content_before_first_anchor, id1, content1, id2, content2, ...]
    # Skip the first part if it exists (content before any anchor)
    start_idx = 1 if len(parts) > 1 else 0
    
    for i in range(start_idx, len(parts), 2):
        if i + 1 < len(parts):
            block_id = parts[i]
            content = parts[i + 1].strip()
            blocks.append((block_id, content))
        elif i < len(parts):
            # Last ID with no content (edge case)
            block_id = parts[i]
            blocks.append((block_id, ""))
    
    logger.info(f"Extracted {len(blocks)} blocks from anchored markdown")
    for block_id, content in blocks:
        content_preview = content[:50].replace('\n', '\\n') if content else "(empty)"
        logger.debug(f"Block {block_id}: {content_preview}...")
    
    return blocks


def get_original_block_content(
    block_id: str,
    annotated_markdown: str
) -> Optional[str]:
    """
    Get the original content of a block from annotated markdown.
    
    Args:
        block_id: Complex block ID (e.g., "blk-a1b2c3d4")
        annotated_markdown: Original annotated markdown
        
    Returns:
        Content of the block or None if not found
    """
    # Pattern to match this specific block's comment and its content
    # Matches: <!-- anything id="blk-xxx" anything -->
    # followed by content until next comment or end
    block_pattern = re.compile(
        rf'<!--[^>]*\sid="{re.escape(block_id)}"[^>]*-->\n?(.*?)(?=<!--|\Z)',
        re.DOTALL
    )
    
    match = block_pattern.search(annotated_markdown)
    if match:
        content = match.group(1).strip()
        return content
    
    logger.warning(f"Could not find content for block {block_id}")
    return None

