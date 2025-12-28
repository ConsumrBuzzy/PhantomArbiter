use pyo3::prelude::*;

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

/// Go/No-Go Decision Engine for Net Profit.
/// Moves float math to Rust to avoid GIL and precision overhead.
#[pyfunction]
fn calculate_net_profit(spread_raw: f64, trade_size: f64, jito_tip: f64, route_friction: f64) -> PyResult<f64> {
    let gross = trade_size * (spread_raw / 100.0);
    let net = gross - jito_tip - route_friction;
    Ok(net)
}

/// Batch processing to eliminate FFI overhead.
/// Processes thousands of trades in a single Rust call.
#[pyfunction]
fn calculate_net_profit_batch(
    spreads: Vec<f64>,
    trade_size: f64,
    jito_tip: f64,
    route_friction: f64
) -> PyResult<Vec<f64>> {
    let mut results = Vec::with_capacity(spreads.len());
    for spread in spreads {
        let gross = trade_size * (spread / 100.0);
        let net = gross - jito_tip - route_friction;
        results.push(net);
    }
    Ok(results)
}

/// A Python module implemented in Rust.
#[pymodule]
fn phantom_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(sum_as_string, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_arb_opportunity, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_net_profit, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_net_profit_batch, m)?)?;
    Ok(())
}
