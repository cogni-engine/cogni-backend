"""Block ID Mapper - Convert between complex and simple block IDs"""
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BlockIdMapper:
    """
    Bidirectional mapper for converting between complex block IDs and simple sequential numbers.
    
    Complex IDs: blk-a1b2c3d4, blk-xyz123
    Simple IDs: 1, 2, 3, 4
    Decimal IDs for insertions: 5.1, 5.2 (insert after block 5)
    """
    
    def __init__(self, block_ids: List[str]):
        """
        Initialize the mapper with a list of block IDs in document order.
        
        Args:
            block_ids: List of complex block IDs in the order they appear in the document
        """
        self._complex_to_simple: Dict[str, str] = {}
        self._simple_to_complex: Dict[str, str] = {}
        
        # Build bidirectional mapping
        for idx, block_id in enumerate(block_ids, start=1):
            simple_id = str(idx)
            self._complex_to_simple[block_id] = simple_id
            self._simple_to_complex[simple_id] = block_id
        
        logger.info(f"Initialized BlockIdMapper with {len(block_ids)} block IDs")
    
    def to_simple_id(self, complex_id: str) -> Optional[str]:
        """
        Convert a complex block ID to a simple sequential number.
        
        Args:
            complex_id: Complex ID like "blk-a1b2c3d4"
            
        Returns:
            Simple ID like "1" or None if not found
        """
        simple_id = self._complex_to_simple.get(complex_id)
        if not simple_id:
            logger.warning(f"Complex ID not found in mapping: {complex_id}")
        return simple_id
    
    def to_complex_id(self, simple_id: str) -> Optional[str]:
        """
        Convert a simple ID (or decimal ID) to a complex block ID.
        
        For decimal IDs (e.g., "5.1"), returns the parent block's complex ID.
        
        Args:
            simple_id: Simple ID like "1" or decimal like "5.1"
            
        Returns:
            Complex ID like "blk-a1b2c3d4" or None if not found
        """
        # Check if this is a decimal ID (insertion)
        if '.' in simple_id:
            parent_id = simple_id.split('.')[0]
            return self._simple_to_complex.get(parent_id)
        
        complex_id = self._simple_to_complex.get(simple_id)
        if not complex_id:
            logger.warning(f"Simple ID not found in mapping: {simple_id}")
        return complex_id
    
    def get_insertion_parent(self, decimal_id: str) -> Optional[Tuple[str, int]]:
        """
        Parse a decimal ID and return the parent block's complex ID and insertion index.
        
        Args:
            decimal_id: Decimal ID like "5.1" or "5.2"
            
        Returns:
            Tuple of (parent_complex_id, insertion_index) or None if invalid
            Example: "5.1" → ("blk-xyz123", 1)
        """
        if '.' not in decimal_id:
            logger.warning(f"Not a decimal ID: {decimal_id}")
            return None
        
        try:
            parts = decimal_id.split('.')
            parent_simple_id = parts[0]
            insertion_index = int(parts[1])
            
            parent_complex_id = self._simple_to_complex.get(parent_simple_id)
            if not parent_complex_id:
                logger.warning(f"Parent block not found for decimal ID: {decimal_id}")
                return None
            
            return (parent_complex_id, insertion_index)
        
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing decimal ID {decimal_id}: {e}")
            return None
    
    def is_decimal_id(self, simple_id: str) -> bool:
        """
        Check if a simple ID is a decimal ID (indicating an insertion).
        
        Args:
            simple_id: ID to check
            
        Returns:
            True if decimal ID, False otherwise
        """
        return '.' in simple_id
    
    def get_all_simple_ids(self) -> List[str]:
        """
        Get all simple IDs in order.
        
        Returns:
            List of simple IDs like ["1", "2", "3", ...]
        """
        # Sort by integer value to maintain order
        return sorted(self._simple_to_complex.keys(), key=lambda x: int(x))
    
    def get_all_complex_ids(self) -> List[str]:
        """
        Get all complex IDs in document order.
        
        Returns:
            List of complex IDs in the order they were provided
        """
        # Return in the order of simple IDs
        return [self._simple_to_complex[simple_id] 
                for simple_id in self.get_all_simple_ids()]

