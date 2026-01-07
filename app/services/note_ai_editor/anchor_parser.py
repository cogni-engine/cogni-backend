"""
Anchor-Based Parser - Convert AI's anchored output to block-level suggestions

This module parses anchor-based markdown output from the AI and converts it to
structured suggestions with block IDs, actions, and content changes.
"""
import re
import logging
from typing import List

from .types import AISuggestionDict
from .id_mapper import BlockIdMapper
from .anchored_markdown import (
    extract_blocks_from_anchored_markdown,
    extract_block_ids_from_annotated_markdown
)

logger = logging.getLogger(__name__)


def is_content_empty_or_minimal(content: str) -> bool:
    """
    Check if content is empty or minimal (indicating a deletion).
    
    Args:
        content: The content to check
        
    Returns:
        True if content should be considered as deleted
    """
    # Remove whitespace and check if empty
    stripped = content.strip()
    return len(stripped) == 0


def parse_anchored_output(
    ai_output: str,
    id_mapper: BlockIdMapper,
    original_annotated_markdown: str
) -> List[AISuggestionDict]:
    """
    Parse AI's anchored output and convert to block-level suggestions.
    
    The AI outputs only changed blocks with their anchors:
    - Edit: <!-- id="2" --> followed by new content
    - Delete: <!-- id="3" --> followed by empty content
    - Insert: <!-- id="5.1" --> for new block after block 5
    
    Multiple insert_after operations for the same block_id are grouped into a single
    suggestion with suggested_text as a list of strings.
    
    Args:
        ai_output: AI's output with anchored blocks
        id_mapper: Mapper to convert simple IDs back to complex IDs
        original_annotated_markdown: Original markdown with complex IDs (for comparison)
        
    Returns:
        List of suggestion dictionaries with block IDs, actions, and text changes
    """
    # First pass: collect all suggestions
    raw_suggestions: List[AISuggestionDict] = []
    
    # Extract all blocks from AI output
    ai_blocks = extract_blocks_from_anchored_markdown(ai_output)
    
    if not ai_blocks:
        logger.warning("No blocks found in AI output")
        return []
    
    logger.info(f"Processing {len(ai_blocks)} blocks from AI output")
    
    for simple_id, new_content in ai_blocks:
        # Check if this is an insertion (decimal ID)
        if id_mapper.is_decimal_id(simple_id):
            # Handle insertion
            insertion_info = id_mapper.get_insertion_parent(simple_id)
            if not insertion_info:
                logger.warning(f"Could not parse insertion ID: {simple_id} - skipping")
                logger.warning(f"Available parent IDs: {id_mapper.get_all_simple_ids()}")
                continue
            
            parent_complex_id, insertion_index = insertion_info
            
            # Insertions are always "insert_after" the parent block
            raw_suggestions.append({
                "block_id": parent_complex_id,
                "action": "insert_after",
                "suggested_text": [new_content]
            })
            logger.info(f"Insertion after block {parent_complex_id} (simple ID {simple_id})")
        
        else:
            # Handle edit or delete
            complex_id = id_mapper.to_complex_id(simple_id)
            if not complex_id:
                logger.error(f"Could not map simple ID '{simple_id}' to complex ID - block does not exist!")
                logger.error(f"Available simple IDs: {id_mapper.get_all_simple_ids()}")
                logger.error("AI may have hallucinated this ID or there's a mapping issue")
                continue
            
            # Check if this is a deletion (empty content)
            if is_content_empty_or_minimal(new_content):
                raw_suggestions.append({
                    "block_id": complex_id,
                    "action": "delete",
                    "suggested_text": None
                })
                logger.info(f"Deletion of block {complex_id} (simple ID {simple_id})")
            
            else:
                # This is an edit/replace
                raw_suggestions.append({
                    "block_id": complex_id,
                    "action": "replace",
                    "suggested_text": [new_content]
                })
                logger.info(f"Edit of block {complex_id} (simple ID {simple_id})")
    
    # Second pass: group multiple insert_after operations for the same block_id
    suggestions_map: dict[tuple[str, str], AISuggestionDict] = {}
    
    for suggestion in raw_suggestions:
        key = (suggestion["block_id"], suggestion["action"])
        
        if key in suggestions_map:
            # Merge with existing suggestion
            existing = suggestions_map[key]
            if suggestion["action"] == "insert_after" and suggestion["suggested_text"]:
                # Append to the list of texts to insert
                if existing["suggested_text"] is None:
                    existing["suggested_text"] = []
                existing["suggested_text"].extend(suggestion["suggested_text"])
                logger.info(f"Grouped multiple insert_after for block {suggestion['block_id']}")
            else:
                # For replace/delete, we keep the first one (shouldn't have duplicates)
                logger.warning(f"Duplicate {suggestion['action']} suggestion for block {suggestion['block_id']}, keeping first")
        else:
            suggestions_map[key] = suggestion
    
    suggestions = list(suggestions_map.values())
    
    logger.info(f"Generated {len(suggestions)} suggestions from anchored output (after grouping)")
    
    # Log summary
    action_counts = {}
    unique_block_ids = set()
    for suggestion in suggestions:
        action = suggestion["action"]
        action_counts[action] = action_counts.get(action, 0) + 1
        unique_block_ids.add(suggestion["block_id"])
    
    logger.info(f"Suggestion summary: {action_counts}")
    logger.info(f"Affected blocks: {len(unique_block_ids)} unique block IDs")
    logger.debug(f"Block IDs in suggestions: {sorted(unique_block_ids)}")
    
    # Validate that all block IDs exist in the original document
    original_block_ids = set(extract_block_ids_from_annotated_markdown(original_annotated_markdown))
    invalid_block_ids = unique_block_ids - original_block_ids
    
    if invalid_block_ids:
        logger.error(f"WARNING: Found {len(invalid_block_ids)} suggestions with non-existent block IDs!")
        logger.error(f"Invalid block IDs: {invalid_block_ids}")
        logger.error(f"Valid block IDs in document: {original_block_ids}")
        # Filter out invalid suggestions
        valid_suggestions = [s for s in suggestions if s["block_id"] in original_block_ids]
        logger.warning(f"Filtered out {len(suggestions) - len(valid_suggestions)} invalid suggestions")
        return valid_suggestions
    
    return suggestions


def validate_anchored_output(ai_output: str) -> bool:
    """
    Validate that the AI output follows the expected anchor format.
    
    Args:
        ai_output: AI's output to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Check for at least one anchor
    anchor_pattern = re.compile(r'<!--\s*id="([^"]+)"\s*-->')
    matches = anchor_pattern.findall(ai_output)
    
    if not matches:
        logger.warning("No anchors found in AI output")
        return False
    
    logger.info(f"Found {len(matches)} anchors in AI output: {matches}")
    return True


def parse_anchored_output_with_validation(
    ai_output: str,
    id_mapper: BlockIdMapper,
    original_annotated_markdown: str
) -> List[AISuggestionDict]:
    """
    Parse AI's anchored output with validation.
    
    This is a wrapper around parse_anchored_output that validates the input first.
    
    Args:
        ai_output: AI's output with anchored blocks
        id_mapper: Mapper to convert simple IDs back to complex IDs
        original_annotated_markdown: Original markdown with complex IDs
        
    Returns:
        List of suggestion dictionaries, or empty list if validation fails
    """
    if not validate_anchored_output(ai_output):
        logger.error("AI output validation failed")
        return []
    
    return parse_anchored_output(ai_output, id_mapper, original_annotated_markdown)

