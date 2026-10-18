const BATCH_SIZE:usize=1024;
struct E { binding:Option<u32>, batch:Option<Vec<u8>>, pending:Option<(usize,Vec<u8>)>, cursor:usize, pack_ceiling:usize }
impl E {
    #[inline(never)] fn guarded(record_cap:Option<usize>)->Self {
        let pack_ceiling=match record_cap {Some(cap) if cap<BATCH_SIZE=>cap.max(1),_=>BATCH_SIZE};
        Self{binding:Some(0),batch:None,pending:None,cursor:0,pack_ceiling}
    }
    #[inline(never)] fn clamped(record_cap:Option<usize>)->Self {
        let pack_ceiling=record_cap.unwrap_or(BATCH_SIZE).clamp(1,BATCH_SIZE);
        Self{binding:Some(0),batch:None,pending:None,cursor:0,pack_ceiling}
    }
}
fn main(){for cap in [None,Some(0),Some(1),Some(10),Some(1023),Some(1024),Some(1025),Some(usize::MAX)]{let cap=std::hint::black_box(cap);let a=E::guarded(cap);let b=E::clamped(cap);println!("{cap:?}: guarded={} clamped={}",a.pack_ceiling,b.pack_ceiling);assert_eq!(b.pack_ceiling,cap.unwrap_or(BATCH_SIZE).clamp(1,BATCH_SIZE));}}
