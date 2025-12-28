use bytemuck::{Pod, Zeroable};
use pyo3::prelude::*;
use base64::{Engine as _, engine::general_purpose};

// ------------------------------------------------------------------------
// PHOENIX MARKET HEADER (Partial Definition)
// ------------------------------------------------------------------------
// We define the fixed-size implementation-agnostic start of the header.
// Full header is large and has nested structs. We target the first 128 bytes.

#[repr(C)]
#[derive(Copy, Clone, Pod, Zeroable)]
struct PhoenixHeaderMin {
    discriminant: u64,
    status: u64,
    // MarketSizeParams is usually 4 * u64 or similar.
    // Let's use a byte array for the rest to avoid padding issues.
    // We just want to prove Zero-Copy casting works.
    _padding: [u8; 112], 
}

// ------------------------------------------------------------------------
// DECODER
// ------------------------------------------------------------------------

#[pyfunction]
pub fn decode_phoenix_header(data_b64: String) -> PyResult<Option<(u64, u64)>> {
    let bytes = general_purpose::STANDARD.decode(data_b64)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("{}", e)))?;

    if bytes.len() < std::mem::size_of::<PhoenixHeaderMin>() {
        return Ok(None);
    }

    // ZERO-COPY CAST
    // We cast the slice to a reference. If alignment is wrong, it fails.
    // Only works if we are extremely careful.
    // Actually, `try_from_bytes` copies if not aligned.
    // `cast_slice` panics.
    // `try_cast_slice` returns Result.
    
    // For safety in Python context, we often just read.
    // But user asked for "bytemuck structs".
    
    let header: &PhoenixHeaderMin = bytemuck::try_from_bytes(&bytes[0..128])
        .map_err(|_| PyErr::new::<pyo3::exceptions::PyValueError, _>("Cast failed"))?;

    Ok(Some((header.discriminant, header.status)))
}
