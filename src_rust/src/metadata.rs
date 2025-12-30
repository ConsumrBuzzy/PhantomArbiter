use pyo3.prelude::*;

#[pyclass]
#[derive(Clone, Default, Debug)]
pub struct SharedTokenMetadata {
    #[pyo3(get, set)]
    pub mint: String,
}

#[pymethods]
impl SharedTokenMetadata {
    #[new]
    fn new(mint: String) -> Self {
        SharedTokenMetadata { mint }
    }
}

pub fn register_metadata_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<SharedTokenMetadata>()?;
    Ok(())
}
