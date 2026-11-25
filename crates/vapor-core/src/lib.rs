//! Host-independent smoke simulation. No renderer, OS or foreign-runtime dependency.
//! The runtime profile is `game-mac-v1`, not a claim of v18 numerical parity.
pub mod breath;
pub mod grid;
pub mod runtime;
pub mod solver;
pub mod render;
pub use runtime::*;
pub use solver::{Field, Metrics, Simulation};

pub mod effects;

pub mod fidelity;

mod transport;
pub use transport::DensityBudget;

mod plume;
pub use plume::ResolvedPlumeOptions;

mod pressure;
pub use pressure::PressureReport;

pub mod field_asset;

pub mod field_sequence;
