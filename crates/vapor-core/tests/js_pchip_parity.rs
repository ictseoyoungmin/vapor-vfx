//! Bit-level identity is not required: Rust f64 and JS double should agree
//! within 1e-10 for the same PCHIP inputs on all supported CPU platforms.
use vapor_core::breath::{Curve,Point};

#[test]
fn original_js_golden_vectors() {
    let source=include_str!("../../../fixtures/pchip_v18.tsv");
    let mut samples=0usize;
    for (line_no,line) in source.lines().enumerate() {
        if line.starts_with('#') || line.trim().is_empty() { continue; }
        let row: Vec<_> = line.split('\t').collect();
        assert_eq!(row.len(),5,"bad fixture at line {}",line_no+1);
        let xs:Vec<f64> = row[1].split(',').map(|v|v.parse().unwrap()).collect();
        let ys:Vec<f64> = row[2].split(',').map(|v|v.parse().unwrap()).collect();
        assert_eq!(xs.len(),ys.len());
        let pts=xs.into_iter().zip(ys).map(|(x,y)|Point{x,y}).collect();
        let c=Curve::new(pts).expect("fixture control points invalid");
        let at:f64=row[3].parse().unwrap();
        let expected:f64=row[4].parse().unwrap();
        let got=c.eval(at).unwrap();
        assert!((got-expected).abs()<=1e-10,"{} x={} expected={} got={}",row[0],at,expected,got);
        samples+=1;
    }
    assert!(samples>=100,"too few vectors: {}",samples);
}
