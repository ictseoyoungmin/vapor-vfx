//! Legacy PCHIP / Fritsch–Carlson curve port from `legacy/v18/src/breath.js`.
//! Invalid/duplicate control points are rejected rather than silently repaired.

use std::error::Error;
use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Point { pub x: f64, pub y: f64 }

#[derive(Debug, Clone, Copy, Eq, PartialEq)]
pub enum CurveError { NotEnoughPoints, NonFiniteValue, RepeatedOrOutOfRangeX, InvalidDuration }
impl fmt::Display for CurveError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f,"{}",match self {
            Self::NotEnoughPoints => "at least 2 control points required",
            Self::NonFiniteValue => "curve input must be finite",
            Self::RepeatedOrOutOfRangeX => "control x values must be unique within 0..1, including endpoints",
            Self::InvalidDuration => "duration must be within 0.4..8 seconds",
        })
    }
}
impl Error for CurveError {}

#[derive(Clone, Debug, PartialEq)]
pub struct Curve { points: Vec<Point>, tangents: Vec<f64> }

impl Curve {
    pub fn new(mut points: Vec<Point>) -> Result<Self, CurveError> {
        if points.len() < 2 { return Err(CurveError::NotEnoughPoints); }
        if points.iter().any(|p| !p.x.is_finite() || !p.y.is_finite()) { return Err(CurveError::NonFiniteValue); }
        points.sort_by(|a,b| a.x.total_cmp(&b.x));
        if points[0].x != 0.0 || points[points.len()-1].x != 1.0 ||
           points.windows(2).any(|p| p[0].x >= p[1].x) { return Err(CurveError::RepeatedOrOutOfRangeX); }
        let n = points.len();
        let mut d = vec![0.0; n-1];
        let mut m = vec![0.0; n];
        for i in 0..n-1 {
            d[i] = (points[i+1].y-points[i].y)/(points[i+1].x-points[i].x).max(1e-6);
        }
        m[0]=d[0]; m[n-1]=d[n-2];
        for i in 1..n-1 {
            m[i]=if d[i-1]*d[i]<=0.0 {0.0} else {(d[i-1]+d[i])/2.0};
        }
        for i in 0..n-1 {
            if d[i].abs() < 1e-9 { m[i]=0.0; m[i+1]=0.0; continue; }
            let a=m[i]/d[i]; let b=m[i+1]/d[i]; let s=a*a+b*b;
            if s>9.0 { let t=3.0/s.sqrt(); m[i]=t*a*d[i]; m[i+1]=t*b*d[i]; }
        }
        Ok(Self {points,tangents:m})
    }
    pub fn points(&self)->&[Point] { &self.points }
    pub fn eval(&self, x: f64) -> Result<f64, CurveError> {
        if !x.is_finite() { return Err(CurveError::NonFiniteValue); }
        let p=&self.points; let n=p.len();
        if x<=0.0 {return Ok(p[0].y);}
        if x>=1.0 {return Ok(p[n-1].y);}
        let mut i=0;
        while i<n-2 && x>p[i+1].x {i+=1;}
        let h=(p[i+1].x-p[i].x).max(1e-6);
        let t=(x-p[i].x)/h;
        let t2=t*t; let t3=t2*t;
        Ok((2.0*t3-3.0*t2+1.0)*p[i].y + (t3-2.0*t2+t)*h*self.tangents[i]
          +(-2.0*t3+3.0*t2)*p[i+1].y+(t3-t2)*h*self.tangents[i+1])
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BreathSample { pub speed: f64, pub amount: f64, pub density: f64 }

#[derive(Debug, Clone, PartialEq)]
pub struct BreathProfile { pub duration_s: f64, pub speed: Curve, pub amount: Curve, pub density: Curve }
impl BreathProfile {
    pub fn new(duration_s: f64, speed: Curve, amount: Curve, density: Curve) -> Result<Self,CurveError> {
        if !duration_s.is_finite() || !(0.4..=8.0).contains(&duration_s) {return Err(CurveError::InvalidDuration);}
        Ok(Self {duration_s,speed,amount,density})
    }
    pub fn sample_normalized(&self, x: f64) -> Result<BreathSample,CurveError> {
        let speed=self.speed.eval(x)?;
        let amount=self.amount.eval(x)?.clamp(0.0,1.0);
        let density=self.density.eval(x)?.max(0.0);
        Ok(BreathSample {speed,amount,density})
    }
    pub fn sample_seconds(&self, seconds: f64) -> Result<BreathSample,CurveError> {
        if !seconds.is_finite() { return Err(CurveError::NonFiniteValue); }
        self.sample_normalized((seconds/self.duration_s).clamp(0.0,1.0))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn no_overshoot_for_monotone_data() {
        let c=Curve::new(vec![Point{x:0.0,y:0.0},Point{x:0.5,y:1.0},Point{x:1.0,y:1.0}]).unwrap();
        for i in 0..=100 {
            let y=c.eval(i as f64/100.0).unwrap();
            assert!((0.0..=1.0).contains(&y),"y={}",y);
        }
    }
    #[test]
    fn rejects_invalid_points() {
        assert!(Curve::new(vec![Point{x:0.0,y:0.0}]).is_err());
        assert!(Curve::new(vec![Point{x:0.0,y:0.0},Point{x:0.0,y:1.0},Point{x:1.0,y:1.0}]).is_err());
        assert!(Curve::new(vec![Point{x:0.0,y:f64::NAN},Point{x:1.0,y:0.0}]).is_err());
    }
}
