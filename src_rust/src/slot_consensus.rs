// ------------------------------------------------------------------------
// SLOT CONSENSUS (The Accuracy Guard)
// Phase 17: De-duplication and slot validation for parallel WSS streams
// ------------------------------------------------------------------------
//
// When multiple RPC nodes send logs for the same event, we need to:
// 1. Accept only the FIRST arrival (de-duplication)
// 2. Reject data from lower slots (stale detection)
// 3. Track slot progression (fork detection)

use pyo3::prelude::*;
use std::collections::HashSet;
use std::sync::Mutex;
use std::time::{Duration, Instant};

// ============================================================================
// BLOOM FILTER FOR SIGNATURE DE-DUPLICATION
// ============================================================================

/// Simple bloom-like filter using a rolling hash set.
/// We use a HashSet with TTL-based eviction instead of a true Bloom filter
/// for simplicity and zero false-positive guarantee.
#[pyclass]
pub struct SignatureDedup {
    /// Set of recently seen signatures
    seen: Mutex<HashSet<String>>,
    /// Maximum size before forced eviction
    max_size: usize,
    /// Signatures to evict when max_size is reached
    eviction_batch: usize,
}

#[pymethods]
impl SignatureDedup {
    #[new]
    #[pyo3(signature = (max_size=10000))]
    pub fn new(max_size: usize) -> Self {
        Self {
            seen: Mutex::new(HashSet::with_capacity(max_size)),
            max_size,
            eviction_batch: max_size / 4, // Evict 25% when full
        }
    }
    
    /// Check if a signature is new (not seen before).
    /// Returns true if this is the FIRST time we've seen this signature.
    /// Returns false if it's a duplicate.
    pub fn is_new(&self, signature: String) -> bool {
        let mut seen = self.seen.lock().unwrap();
        
        // If at capacity, evict oldest (random eviction for simplicity)
        if seen.len() >= self.max_size {
            let to_remove: Vec<_> = seen.iter().take(self.eviction_batch).cloned().collect();
            for sig in to_remove {
                seen.remove(&sig);
            }
        }
        
        // Insert returns true if the value was NOT present
        seen.insert(signature)
    }
    
    /// Clear all seen signatures.
    pub fn clear(&self) {
        let mut seen = self.seen.lock().unwrap();
        seen.clear();
    }
    
    /// Get current size of the dedup filter.
    pub fn size(&self) -> usize {
        self.seen.lock().unwrap().len()
    }
}

// ============================================================================
// SLOT TRACKER FOR STALE DATA DETECTION
// ============================================================================

/// Tracks the latest slot seen per provider/source.
/// Rejects data from slots lower than the current maximum.
#[pyclass]
pub struct SlotTracker {
    /// Latest confirmed slot across all providers
    latest_slot: Mutex<u64>,
    /// Highest slot seen per provider (for debugging)
    per_provider_slots: Mutex<Vec<(String, u64)>>,
    /// Window of acceptable slot difference
    max_slot_lag: u64,
}

#[pymethods]
impl SlotTracker {
    #[new]
    #[pyo3(signature = (max_slot_lag=2))]
    pub fn new(max_slot_lag: u64) -> Self {
        Self {
            latest_slot: Mutex::new(0),
            per_provider_slots: Mutex::new(Vec::new()),
            max_slot_lag,
        }
    }
    
    /// Update the tracker with a new slot from a provider.
    /// 
    /// Returns:
    /// - 1 if this slot is newer (accepted)
    /// - 0 if this slot is current (accepted)
    /// - -1 if this slot is stale (rejected)
    pub fn update_slot(&self, provider: String, slot: u64) -> i32 {
        let mut latest = self.latest_slot.lock().unwrap();
        let mut providers = self.per_provider_slots.lock().unwrap();
        
        // Update per-provider tracking
        let mut found = false;
        for (p, s) in providers.iter_mut() {
            if p == &provider {
                *s = slot.max(*s);
                found = true;
                break;
            }
        }
        if !found {
            providers.push((provider, slot));
        }
        
        // Check against global latest
        if slot > *latest {
            *latest = slot;
            1 // Newer
        } else if slot >= latest.saturating_sub(self.max_slot_lag) {
            0 // Current (within acceptable lag)
        } else {
            -1 // Stale
        }
    }
    
    /// Check if a slot is acceptable (not stale).
    pub fn is_acceptable(&self, slot: u64) -> bool {
        let latest = self.latest_slot.lock().unwrap();
        slot >= latest.saturating_sub(self.max_slot_lag)
    }
    
    /// Get the current latest slot.
    pub fn get_latest_slot(&self) -> u64 {
        *self.latest_slot.lock().unwrap()
    }
    
    /// Get all provider slots for debugging.
    pub fn get_provider_slots(&self) -> Vec<(String, u64)> {
        self.per_provider_slots.lock().unwrap().clone()
    }
    
    /// Reset the tracker (e.g., on reconnection).
    pub fn reset(&self) {
        *self.latest_slot.lock().unwrap() = 0;
        self.per_provider_slots.lock().unwrap().clear();
    }
}

// ============================================================================
// CONSENSUS ENGINE (COMBINES DEDUP + SLOT TRACKING)
// ============================================================================

/// High-performance message filter for the parallel WSS race.
/// 
/// Combines:
/// - Signature de-duplication (first-in wins)
/// - Slot validation (reject stale data)
/// - Provider health inference
#[pyclass]
pub struct ConsensusEngine {
    dedup: SignatureDedup,
    slot_tracker: SlotTracker,
    /// Count of accepted messages
    accepted_count: Mutex<u64>,
    /// Count of rejected duplicates
    duplicate_count: Mutex<u64>,
    /// Count of rejected stale messages
    stale_count: Mutex<u64>,
}

#[pymethods]
impl ConsensusEngine {
    #[new]
    #[pyo3(signature = (max_signatures=10000, max_slot_lag=2))]
    pub fn new(max_signatures: usize, max_slot_lag: u64) -> Self {
        Self {
            dedup: SignatureDedup::new(max_signatures),
            slot_tracker: SlotTracker::new(max_slot_lag),
            accepted_count: Mutex::new(0),
            duplicate_count: Mutex::new(0),
            stale_count: Mutex::new(0),
        }
    }
    
    /// Process an incoming message from a provider.
    /// 
    /// Returns true if the message should be processed (first arrival, valid slot).
    /// Returns false if it should be dropped (duplicate or stale).
    /// 
    /// # Arguments
    /// * `provider` - Provider identifier (e.g., "helius", "alchemy")
    /// * `signature` - Transaction signature
    /// * `slot` - Slot number
    pub fn should_process(&self, provider: String, signature: String, slot: u64) -> bool {
        // 1. Check slot freshness
        let slot_status = self.slot_tracker.update_slot(provider, slot);
        if slot_status < 0 {
            *self.stale_count.lock().unwrap() += 1;
            return false;
        }
        
        // 2. Check for duplicate
        if !self.dedup.is_new(signature) {
            *self.duplicate_count.lock().unwrap() += 1;
            return false;
        }
        
        // 3. Accept!
        *self.accepted_count.lock().unwrap() += 1;
        true
    }
    
    /// Quick check if a slot is acceptable (without full processing).
    pub fn is_slot_fresh(&self, slot: u64) -> bool {
        self.slot_tracker.is_acceptable(slot)
    }
    
    /// Get statistics for monitoring.
    pub fn get_stats(&self) -> (u64, u64, u64, u64) {
        let accepted = *self.accepted_count.lock().unwrap();
        let duplicates = *self.duplicate_count.lock().unwrap();
        let stale = *self.stale_count.lock().unwrap();
        let latest_slot = self.slot_tracker.get_latest_slot();
        (accepted, duplicates, stale, latest_slot)
    }
    
    /// Reset all statistics.
    pub fn reset_stats(&self) {
        *self.accepted_count.lock().unwrap() = 0;
        *self.duplicate_count.lock().unwrap() = 0;
        *self.stale_count.lock().unwrap() = 0;
    }
    
    /// Get dedup filter size.
    pub fn dedup_size(&self) -> usize {
        self.dedup.size()
    }
    
    /// Force clear the dedup filter.
    pub fn clear_dedup(&self) {
        self.dedup.clear();
    }
}

// ============================================================================
// MODULE REGISTRATION
// ============================================================================

pub fn register_consensus_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<SignatureDedup>()?;
    m.add_class::<SlotTracker>()?;
    m.add_class::<ConsensusEngine>()?;
    Ok(())
}
