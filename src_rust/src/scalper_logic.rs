use pyo3.prelude::*;
use crate::metadata::SharedTokenMetadata;

#[pyclass]
#[derive(Clone, Debug)]
pub struct ScalpSignal {
    #[pyo3(get)]
    pub token: String,
}

#[pyclass]
pub struct SignalScanner {}

#[pymethods]
impl SignalScanner {
    #[new]
    fn new() -> Self {
        SignalScanner {}
    }
    
    fn scan_scalp_opportunities(&self, _registry: Vec<SharedTokenMetadata>) -> Vec<ScalpSignal> {
        vec![]
    }
}

pub fn register_scalper_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<ScalpSignal>()?;
    m.add_class::<SignalScanner>()?;
    Ok(())
}
