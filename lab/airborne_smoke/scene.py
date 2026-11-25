"""Software projection of a fictional quadcopter model and compositing of baked Lab volume frames."""
import numpy as np, math, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import os
W=Path(os.environ.get("VAPOR_AIRBORNE_OUTPUT", Path(__file__).resolve().parents[2]/"reports/local/lab/airborne-smoke")).resolve()
w,h=960,540; ss=2; camera=np.array([7.0,5.55,-13.0]); focal=h*.5/math.tan(math.radians(34/2)); sun=np.array([.76,.64,-.18]);sun/=np.linalg.norm(sun)
faces=[]
def poly(v,c,a=255,unlit=False): faces.append((np.array(v,dtype=float),np.array(c,dtype=float),a,unlit))
def ring_box(center,dims,colors):
 cx,cy,cz=center; x,y,z=np.array(dims)/2; b=min(x,z)*.31
 shape=[(-x+b,-z),(x-b,-z),(x,-z+b),(x,z-b),(x-b,z),(-x+b,z),(-x,z-b),(-x,-z+b)]
 rings=[]
 for yy,s in [(-y,.83),(-y*.66,1),(y*.65,1),(y,.78)]: rings.append([(cx+xx*s,cy+yy,cz+zz*s) for xx,zz in shape])
 for i in range(len(rings)-1):
  for j in range(8):poly([rings[i][j],rings[i][(j+1)%8],rings[i+1][(j+1)%8],rings[i+1][j]],colors[i])
 poly(rings[-1][::-1],colors[-1]);poly(rings[0],colors[0])
def tube(a,b,r1,r2,col,n=12):
 a=np.array(a);b=np.array(b);axis=b-a;axis=axis/np.linalg.norm(axis);v=np.cross(axis,[0,1,0] if abs(axis[1])<.8 else [0,0,1]);v/=np.linalg.norm(v);u=np.cross(axis,v)
 A=[a+r1*(v*math.cos(j*2*math.pi/n)+u*math.sin(j*2*math.pi/n)) for j in range(n)];B=[b+r2*(v*math.cos(j*2*math.pi/n)+u*math.sin(j*2*math.pi/n)) for j in range(n)]
 for j in range(n):poly([A[j],A[(j+1)%n],B[(j+1)%n],B[j]],col)
 poly(A[::-1],col);poly(B,col)
def sphere(center,scale,col,n=16,m=8):
 c=np.array(center);s=np.array(scale);rings=[]
 for k in range(m+1):
  t=-math.pi/2+math.pi*k/m;rings.append([c+s*np.array([math.cos(t)*math.cos(j*2*math.pi/n),math.sin(t),math.cos(t)*math.sin(j*2*math.pi/n)]) for j in range(n)])
 for k in range(m):
  for j in range(n):poly([rings[k][j],rings[k][(j+1)%n],rings[k+1][(j+1)%n],rings[k+1][j]],col)
# Body shell, underside, camera, colored seam and decorative lights.
ring_box([0,-.045,0],[.69,.28,.88],[[.075,.09,.105],[.15,.16,.17],[.27,.29,.31],[.33,.35,.37]])
ring_box([0,.12,-.015],[.64,.22,.83],[[.32,.35,.38],[.62,.65,.66],[.79,.80,.79],[.86,.88,.87]])
ring_box([0,.225,.03],[.27,.035,.40],[[.21,.23,.25],[.28,.30,.31],[.33,.36,.37],[.37,.40,.42]])
ring_box([0,-.205,-.29],[.35,.23,.30],[[.06,.075,.085],[.12,.14,.15],[.19,.21,.23],[.24,.25,.27]])
sphere([0,-.23,-.47],[.106,.106,.065],[.065,.08,.10]);sphere([0,-.23,-.513],[.065,.064,.018],[.105,.20,.30]);sphere([-.025,-.20,-.527],[.015,.012,.005],[.62,.79,.89],8,4)
rotors=[]
for side in (-1,1):
 for front in (-1,1):
  a=[side*.25,.02,front*.27];b=[side*1.02,.05,front*.78];rotors.append((side,front,b))
  tube(a,b,.092,.064,[.18,.21,.24],10)
  # light upper structural shell and dark motor housing.
  tube([side*.28,.075,front*.29],[side*.88,.087,front*.68],.061,.045,[.56,.58,.59],8)
  tube([b[0],-.045,b[2]],[b[0],.16,b[2]],.147,.132,[.27,.29,.30],16)
  tube([b[0],.15,b[2]],[b[0],.196,b[2]],.123,.11,[.065,.08,.095],16)
  tube([b[0],.19,b[2]],[b[0],.238,b[2]],.06,.045,[.36,.39,.40],12)
  sphere([side*.82,.03,front*.65],[.045,.037,.045],[.22,.79,.60] if front==1 else [.92,.22,.09],8,4)
base_faces=list(faces)
def rotation(yaw,pitch,roll):
 cy,sy=math.cos(yaw),math.sin(yaw);cp,sp=math.cos(pitch),math.sin(pitch);cr,sr=math.cos(roll),math.sin(roll)
 return np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])@np.array([[1,0,0],[0,cp,-sp],[0,sp,cp]])@np.array([[cr,-sr,0],[sr,cr,0],[0,0,1]])
def drone(t,event):
 global faces
 # Intended visual flight; positions are arbitrary scene coordinates.
 a=min(t/event,1);p=np.array([14.0-6.45*a,3.3+.12*math.sin(t*4)*(1-a),4.7]);R=rotation(.48-.12*a,-.075+.028*math.sin(3*t),-.09+.08*math.sin(t*2.3))
 faces=list(base_faces)
 for side,front,b in rotors:
  cx,_,cz=b; y=.244; radius=.42
  # Translucent rotor blur and a few broad stylized blade shapes.
  poly([[cx+radius*math.cos(q*2*math.pi/36),y,cz+radius*math.sin(q*2*math.pi/36)] for q in range(36)],[.08,.12,.15],25,True)
  angle=(t*36*side*front+side*1.2+front*.9)
  for k in range(4):
   phi=angle+k*.33;al=45 if k<3 else 130
   for sign in (-1,1):
    vv=[]
    for lx,lz in [(.035,-.045),(.22,-.07),(.40,-.035),(.43,.012),(.27,.042),(.04,.031)]:
     lx*=sign;lz*=sign;vv.append([cx+lx*math.cos(phi)-lz*math.sin(phi),y+.001*k,cz+lx*math.sin(phi)+lz*math.cos(phi)])
    poly(vv,[.08,.105,.12],al,True)
 layer=Image.new('RGBA',(w*ss,h*ss));draw=ImageDraw.Draw(layer)
 projected=[]
 for v,col,alpha,unlit in faces:
  q=v@R.T+p; z=q[:,2]-camera[2]; px=-(q[:,0]-camera[0])*focal/z+w/2;py=h/2-(q[:,1]-camera[1])*focal/z
  n=np.cross(q[1]-q[0],q[2]-q[0]);norm=np.linalg.norm(n);n=n/norm if norm>1e-8 else np.array([0,1,0]); # use outward-facing normal for stylized diffuse
  view=camera-q.mean(axis=0)
  if np.dot(n,view)<0:n=-n
  lam=max(0,float(np.dot(n,sun))); fac=1 if unlit else (.42+.58*lam+.10*max(0,n[1]));
  # Material is display RGB; ambient lift makes silhouette readable.
  rgb=np.clip(col*fac*255+np.array([7,9,12])*(0 if unlit else 1),0,255).astype(int)
  projected.append((float(z.mean()),list(zip(px*ss,py*ss)),tuple(rgb.tolist())+(alpha,)))
 for _,pts,c in sorted(projected,key=lambda a:-a[0]):draw.polygon(pts,fill=c)
 return layer.resize((w,h),Image.Resampling.LANCZOS)

def render_frame(idx,cfg):
 t=idx/24;evt=cfg['event'];k=t*cfg['fps'];lo=int(k);hi=lo+1;f=k-lo
 def get(i):
  if i<=round(evt*cfg['fps']):i=0
  i=min(i,round(cfg['duration']*cfg['fps']));path=W/'renders'/f'{i:04d}.rgba'
  return Image.frombytes('RGBA',(w,h),path.read_bytes()).convert('RGB')
 base=get(lo);frame=base if f<1e-6 else Image.blend(base,get(hi),f)
 if t<evt+.12:
  d=drone(t,evt);a=np.asarray(d.getchannel('A'),dtype=np.float32)
  if t>evt:
   # A true volume alpha mask from the rendered field covers the model during the transition.
   def mask(i):
    path=W/'renders'/f'{i:04d}.alpha';return np.fromfile(path,dtype='<f4').reshape(h,w) if path.exists() else np.zeros((h,w),np.float32)
   a*=np.clip(1-(mask(lo)*(1-f)+mask(hi)*f),0,1)*max(0,1-(t-evt)/.12)
  d.putalpha(Image.fromarray(a.astype(np.uint8)));frame.paste(d,(0,0),d)
 # Short exposure bloom from the actual emissive volume, not a smoke image overlay.
 if evt<t<evt+.48:
  im=np.asarray(frame,dtype=np.float32);rgb=np.maximum(0,(im[...,0]-190)/65)*np.maximum(0,(im[...,0]-im[...,2]-20)/100);rgb=np.clip(rgb,0,1)
  bloom=np.array(Image.fromarray((rgb*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(9)),dtype=np.float32)/255
  im+=bloom[...,None]*np.array([42,21,5]);frame=Image.fromarray(np.clip(im,0,255).astype(np.uint8))
 return frame
if __name__=='__main__':
 cfg=json.loads((W/'config.json').read_text());(W/'scene').mkdir(exist_ok=True)
 for i in range(round(cfg['duration']*24)+1):render_frame(i,cfg).save(W/'scene'/f'{i:04d}.jpg',quality=96,subsampling=0)
 print('composited',round(cfg['duration']*24)+1,'frames')
