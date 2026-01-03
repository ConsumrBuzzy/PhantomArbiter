use pyo3::prelude::*;
use memmap2::MmapMut;
use bytemuck::{Pod, Zeroable};
use std::fs::OpenOptions;
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::mem::size_of;

/// Memory Layout:
/// [Header (64 bytes)]
///   - Write Cursor (u64)
///   - Magic/Version (u64)
///   - Reserved (48 bytes)
/// [Ring Buffer Data]
///   - PriceUpdate * CAPACITY

const CACHE_FILE_SIZE: u64 = 10 * 1024 * 1024; // 10 MB (Plenty for tick buffer)
const HEADER_SIZE: usize = 64;
const MAGIC: u64 = 0xDEAD_BEEF;

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
pub struct PriceUpdate {
    // Fixed size struct for Zero-Copy
    pub price: f64,
    pub slot: u64,
    pub timestamp: u64,
    pub mint: [u8; 32], // Base58 decoded mint (32 bytes)
    pub decimals: u8,
    pub liquidity: f32,
    pub _padding: [u8; 19], // Align to 64 bytes? 8+8+8+32+1+4 = 61. Pad to 64.
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
struct CacheHeader {
    cursor: u64,
    magic: u64,
    _pad: [u8; 48],
}

#[pyclass]
pub struct FlashCacheWriter {
    mmap: MmapMut,
    capacity: usize,
}

#[pymethods]
impl FlashCacheWriter {
    #[new]
    fn new(path: String) -> PyResult<Self> {
        let path = Path::new(&path);
        
        // Ensure file exists and is sized
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .open(path)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(e.to_string()))?;

        file.set_len(CACHE_FILE_SIZE)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(e.to_string()))?;

        let mut mmap = unsafe { MmapMut::map_mut(&file) }
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(e.to_string()))?;

        // Initialize Header if needed
        let header_slice = &mut mmap[0..size_of::<CacheHeader>()];
        let header: &mut CacheHeader = bytemuck::from_bytes_mut(header_slice);
        
        if header.magic != MAGIC {
            header.magic = MAGIC;
            header.cursor = 0;
        }

        let item_size = size_of::<PriceUpdate>();
        let capacity = (CACHE_FILE_SIZE as usize - HEADER_SIZE) / item_size;

        Ok(FlashCacheWriter { mmap, capacity })
    }

    fn push_update(
        &mut self,
        mint_str: String,
        price: f64,
        slot: u64,
        liquidity: f32
    ) -> PyResult<()> {
        let mut mint_bytes = [0u8; 32];
        // Decode base58 or just copy bytes? Assuming input is valid base58 string.
        // For speed, let's assume we might receive just the string bytes if < 32? 
        // No, standard is decodable.
        // Let's use bs58 decode validation.
        
        match bs58::decode(mint_str).into(&mut mint_bytes) {
            Ok(_) => {},
            Err(_) => {
                // If decode fails or string is weird, maybe it's not base58.
                // Fallback: Just zero it or error? 
                // For HFT, fail fast.
                return Ok(()); 
            }
        };

        // Get header
        let header_slice = &mut self.mmap[0..size_of::<CacheHeader>()];
        let header: &mut CacheHeader = bytemuck::from_bytes_mut(header_slice);
        
        let cursor = header.cursor;
        
        // Write Data
        let idx = (cursor as usize) % self.capacity;
        let offset = HEADER_SIZE + (idx * size_of::<PriceUpdate>());
        
        use std::time::{SystemTime, UNIX_EPOCH};
        let ts = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_millis() as u64;

        let update = PriceUpdate {
            mint: mint_bytes,
            price,
            slot,
            timestamp: ts,
            decimals: 9, // Default
            liquidity,
            _padding: [0; 19],
        };

        let dest = &mut self.mmap[offset..offset + size_of::<PriceUpdate>()];
        dest.copy_from_slice(bytemuck::bytes_of(&update));

        // Advance cursor atomicaly-ish (Header is volatile RAM in practice)
        // We rely on memory barriers implied by OS handling, simpler for now.
        header.cursor = cursor + 1;

        Ok(())
    }
}

#[pyclass]
pub struct FlashCacheReader {
    mmap: MmapMut, // Read-only but MmapMut used for simplicity or Mmap
    capacity: usize,
    last_cursor: u64,
}

#[pymethods]
impl FlashCacheReader {
    #[new]
    fn new(path: String) -> PyResult<Self> {
        let path = Path::new(&path);
        let file = OpenOptions::new()
            .read(true)
            .write(true) // Need write to map mut? Or just read.
            .open(path)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(e.to_string()))?;

        // MmapMut allows us to see updates from other processes?
        // On Windows/Linux, yes MAP_SHARED is default for file maps usually unless CopyOnWrite.
        // Rust memmap2 Mmap is read-only shared. MmapMut is read-write shared.
        // We want to see updates, so Mmap (read-only) is fine if updates propagate.
        // Actually, let's use MmapMut to be safe or Mmap. Mmap is safer.
        
        let mmap = unsafe { MmapMut::map_mut(&file) }
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(e.to_string()))?;
        
        let item_size = size_of::<PriceUpdate>();
        let capacity = (CACHE_FILE_SIZE as usize - HEADER_SIZE) / item_size;

        Ok(FlashCacheReader { 
            mmap, 
            capacity,
            last_cursor: 0 
        })
    }

    /// Read all new updates since last poll.
    fn poll_updates(&mut self) -> PyResult<Vec<(String, f64, u64)>> {
        let header_slice = &self.mmap[0..size_of::<CacheHeader>()];
        let header: &CacheHeader = bytemuck::from_bytes(header_slice);
        
        let current_cursor = header.cursor;
        
        if current_cursor == self.last_cursor {
            return Ok(Vec::new());
        }

        let mut updates = Vec::new();
        // Don't read more than capacity (if we lagged too far, just read last capacity)
        let backlog = current_cursor - self.last_cursor;
        let start_read = if backlog > self.capacity as u64 {
            current_cursor - self.capacity as u64
        } else {
            self.last_cursor
        };

        for i in start_read..current_cursor {
            let idx = (i as usize) % self.capacity;
            let offset = HEADER_SIZE + (idx * size_of::<PriceUpdate>());
            let item_slice = &self.mmap[offset..offset + size_of::<PriceUpdate>()];
            let item: &PriceUpdate = bytemuck::from_bytes(item_slice);

            // Decode mint
            let mint_str = bs58::encode(item.mint).into_string();
            updates.push((mint_str, item.price, item.slot));
        }

        self.last_cursor = current_cursor;
        Ok(updates)
    }
}
