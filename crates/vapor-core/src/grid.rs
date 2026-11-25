//! Mirror `src/fluid.js` DOMAIN / QUALITY / tilesFor / fine grid budgeting.
//! The original atlas is a WebGL2 encoding detail. The Grid3 representation
//! will also be usable for a native 3D-storage-texture wgpu implementation.

use std::error::Error;
use std::fmt;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Domain {
    pub width: f64,
    pub height: f64,
    pub depth: f64,
}
impl Default for Domain {
    fn default() -> Self {
        Self { width: 0.64, height: 0.84, depth: 0.74 }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Quality { Low, Mid, High, Ultra }

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct QualitySettings {
    pub cell: f64,
    pub up: f64,
    pub sor_iterations: u32,
    pub ray_steps: u32,
    pub step_scale: f64,
    pub render_scale: f64,
    pub light_every: u32,
}
impl Quality {
    pub fn settings(self) -> QualitySettings {
        match self {
            Quality::Low => QualitySettings { cell: 0.0125, up: 2.0, sor_iterations: 10, ray_steps: 80, step_scale: 0.9, render_scale: 0.60, light_every: 3 },
            Quality::Mid => QualitySettings { cell: 0.0090, up: 2.0, sor_iterations: 12, ray_steps: 110, step_scale: 0.75, render_scale: 0.75, light_every: 2 },
            Quality::High => QualitySettings { cell: 0.0070, up: 2.0, sor_iterations: 14, ray_steps: 150, step_scale: 0.62, render_scale: 0.85, light_every: 2 },
            Quality::Ultra => QualitySettings { cell: 0.0055, up: 1.5, sor_iterations: 16, ray_steps: 200, step_scale: 0.55, render_scale: 1.00, light_every: 1 },
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AtlasGrid {
    pub nx: u32, pub ny: u32, pub nz: u32,
    pub tiles_x: u32, pub tiles_y: u32,
    pub atlas_width: u32, pub atlas_height: u32,
    pub voxel_count: u64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct GridLayout {
    pub coarse: AtlasGrid,
    pub fine: AtlasGrid,
    pub cell_size_m: f64,
    pub fine_cell_m: f64,
    pub effective_up: f64,
}

#[derive(Debug, Clone, Copy, Eq, PartialEq)]
pub enum GridError { InvalidConfig, DimensionsOverflow, ExceedsDeviceLimits }
impl fmt::Display for GridError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", match self {
            Self::InvalidConfig => "invalid grid parameters",
            Self::DimensionsOverflow => "grid dimensions exceed addressable integers",
            Self::ExceedsDeviceLimits => "even minimum fine grid exceeds device limits",
        })
    }
}
impl Error for GridError {}

fn ceil_to_u32(v: f64) -> Result<u32, GridError> {
    if !v.is_finite() || v < 0. || v > u32::MAX as f64 { return Err(GridError::DimensionsOverflow); }
    Ok(v.ceil() as u32)
}

impl AtlasGrid {
    fn new(nx: u32, ny: u32, nz: u32) -> Result<Self, GridError> {
        if nx == 0 || ny == 0 || nz == 0 { return Err(GridError::InvalidConfig); }
        // The exact WebGL2 tilesFor algorithm, not a generic texel packer.
        let tx = ceil_to_u32(((nz as f64 * ny as f64) / nx as f64).sqrt())?.max(1);
        let ty = nz.div_ceil(tx);
        let w = nx.checked_mul(tx).ok_or(GridError::DimensionsOverflow)?;
        let h = ny.checked_mul(ty).ok_or(GridError::DimensionsOverflow)?;
        let count = nx as u64 * ny as u64 * nz as u64;
        Ok(Self { nx, ny, nz, tiles_x: tx, tiles_y: ty, atlas_width: w, atlas_height: h, voxel_count: count })
    }
    pub fn atlas_xy(self, x: u32, y: u32, z: u32) -> Option<(u32, u32)> {
        if x >= self.nx || y >= self.ny || z >= self.nz { return None; }
        Some(((z % self.tiles_x)*self.nx + x, (z/self.tiles_x)*self.ny + y))
    }
    pub fn voxel_atlas_linear(self, x: u32, y: u32, z: u32) -> Option<u64> {
        let (ax, ay) = self.atlas_xy(x,y,z)?;
        Some((ay as u64 * self.atlas_width as u64 + ax as u64)*4)
    }
}

impl GridLayout {
    pub const FINE_VOXEL_BUDGET: u64 = 11_000_000;
    pub fn new(domain: Domain, quality: Quality, max_texture: u32) -> Result<Self, GridError> {
        let q = quality.settings();
        if max_texture == 0 || !q.cell.is_finite() || q.cell <= 0.0 ||
            !domain.width.is_finite() || !domain.height.is_finite() || !domain.depth.is_finite() ||
            domain.width <= 0.0 || domain.height <= 0.0 || domain.depth <= 0.0 { return Err(GridError::InvalidConfig); }
        // JS Math.round for positive values == floor(value+0.5).
        let f = |m: f64| -> Result<u32, GridError> { ceil_to_u32((m/q.cell + 0.5).floor().max(24.0)) };
        let coarse = AtlasGrid::new(f(domain.width)?,f(domain.height)?,f(domain.depth)?)?;
        if coarse.atlas_width > max_texture || coarse.atlas_height > max_texture {
            return Err(GridError::ExceedsDeviceLimits);
        }
        let mut up = q.up;
        for _ in 0..32 {
            let fine = AtlasGrid::new(ceil_to_u32(coarse.nx as f64 * up)?,
                                      ceil_to_u32(coarse.ny as f64 * up)?,
                                      ceil_to_u32(coarse.nz as f64 * up)?)?;
            if fine.atlas_width <= max_texture && fine.atlas_height <= max_texture &&
                fine.voxel_count <= Self::FINE_VOXEL_BUDGET {
                return Ok(Self { coarse, fine, cell_size_m: q.cell, fine_cell_m: q.cell / up, effective_up: up });
            }
            if up <= 1.0 { break; }
            up = (up - 0.25).max(1.0);
        }
        // In v18 this condition would silently fall through and attempt an invalid
        // render target; explicit error is an intentional safety improvement.
        Err(GridError::ExceedsDeviceLimits)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn low_matches_legacy() {
        let g = GridLayout::new(Domain::default(), Quality::Low, 16384).unwrap();
        assert_eq!((g.coarse.nx, g.coarse.ny, g.coarse.nz), (51,67,59));
        assert_eq!((g.coarse.atlas_width, g.coarse.atlas_height), (459,469));
        assert_eq!(g.fine.voxel_count, 1_612_824);
        assert_eq!((g.fine.atlas_width,g.fine.atlas_height), (1326,1340));
        assert_eq!(g.coarse.atlas_xy(1,2,1),Some((52,2)));
        assert_eq!(g.coarse.atlas_xy(51,2,0),None);
    }
    #[test]
    fn all_quality_presets_match_source_contract() {
        let presets = [
          (Quality::Mid,(71,93,82),4_331_568_u64),
          (Quality::High,(91,120,106),9_260_160_u64),
          (Quality::Ultra,(116,153,135),8_124_060_u64),
        ];
        for (q,c,fine_count) in presets {
            let g=GridLayout::new(Domain::default(),q,16384).unwrap();
            assert_eq!((g.coarse.nx,g.coarse.ny,g.coarse.nz),c);
            assert_eq!(g.fine.voxel_count,fine_count);
        }
    }
    #[test]
    fn strict_device_limit_error() {
        assert_eq!(GridLayout::new(Domain::default(),Quality::Low,100),Err(GridError::ExceedsDeviceLimits));
    }
}
