use vapor_core::field_asset::BakedField;
const RAW:&[u8]=include_bytes!("../../../fixtures/field-asset.vpf");
#[test]fn python_js_fixture(){let f=BakedField::decode(RAW).unwrap();assert_eq!(f.grid.cells,[4,5,6]);assert_eq!(f.grid.extent,[1.,2.,3.]);assert_eq!(f.time,1.25);assert_eq!(f.fields.density[3],3./128.);assert_eq!(f.encode().unwrap().as_slice(),RAW);}
#[test]fn rejects_bad_header_and_payload(){for i in [0,4,8,20,64,68,72,76,80]{let mut b=RAW.to_vec();b[i]^=255;assert!(BakedField::decode(&b).is_err());}assert!(BakedField::decode(&RAW[..RAW.len()-1]).is_err());}
#[test]fn rejects_nonfinite_encode(){let mut f=BakedField::decode(RAW).unwrap();f.fields.density[0]=f32::NAN;assert!(f.encode().is_err());}
