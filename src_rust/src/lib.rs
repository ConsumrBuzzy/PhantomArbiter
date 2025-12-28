use pyo3.prelude::*;

/// Formats the sum of two numbers as string.
#[pyfunction]
fn sum_as_string(a: usize, b: usize) -> PyResult<String> {
    Ok((a + b).to_string())
}

/// A "Hello World" Sniper function to verify fast path execution.
#[pyfunction]
fn calculate_arb_opportunity(
    token_a_price: f64,
    token_b_price: f64,
    fee_bps: f64
) -> PyResult<bool> {
    let spread = (token_b_price - token_a_price) / token_a_price;
    let fee_impact = fee_bps / 10000.0;
    
    // Simple logic: Is spread > fee?
    Ok(spread > fee_impact)
}

/// A Python module implemented in Rust.
#[pymodule]
fn phantom_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(sum_as_string, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_arb_opportunity, m)?)?;
    Ok(())
}
